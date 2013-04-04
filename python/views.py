from .models import GoviniSearch, GoviniSavedSearch, get_user_default_filters
from opencrowd.cab.coreapp import render_to
from govini.esearch.forms import DocumentSearchForm
from .analytics import get_state_bar_graph, get_sector_analytics, get_query_analytics, \
                        get_query_element_analytics, get_sector_analytics_bar, get_query_element_chart,\
                         get_element_result_analytics_chart, get_fomrated_table
from poplicus.baseref.constants import ORG_TYPE_SECTOR_MAPPING
from poplicus.baseref.models import Term, Entity
from govini.govrefdata.models import Industry, GeographyState, GeographyCounty
from govini.govrecordprograms.models import CFDAProgramView
from opencrowd.cab.coreapp import get_paginated_results
from opencrowd.cab.coreapp.utils import get_fake_paginator
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render_to_response
from django.views.decorators.csrf import csrf_exempt
from django.http import HttpResponse
from govini.search import SEARCH_DATA_DOMAIN_ORG, SEARCH_DATA_DOMAIN_PEOPLE,\
                            SEARCH_DATA_DOMAIN_DOCUMENT, SEARCH_DATA_DOMAIN_RECORD,\
                            SEARCH_DATA_DOMAIN_ALL
from govini.esearch.forms import get_form_for_domain, get_procurement_choices, get_grant_choices, get_form_for_domain_facet
from home import default_view
from django.conf import settings
from django.http import QueryDict
from django.template import RequestContext
from opencrowd.cab.coreapp import get_log
from .utils import QueryParser, convert_to_url
from operator import attrgetter
import json, operator, tasks
from datetime import datetime
from django.db.models import Q
from poplicus.snippets.views import get_help_text
from govini.esearch.govini_es_backend import SearchQuerySet


_log = get_log(__name__)

'''Search Settings'''
GOVINI_SEARCH_OVERVIEW_RPP = getattr(settings, 'GOVINI_SEARCH_OVERVIEW_RESULTS_PER_PAGE', 5)
GOVINI_SEARCH_RPP = getattr(settings, 'GOVINI_SEARCH_RESULTS_PER_PAGE', 25)



def get_analytics_for_domain(sqs, data_domain):
    # State Analytic
    if data_domain == SEARCH_DATA_DOMAIN_PEOPLE:
        states_raw = sqs.facet_counts().get('fields', {}).get('loc_state', [])
        if len(states_raw) > 5:
            states_raw = states_raw[:5]
        states = [state for state in states_raw if state[1] > 0]
        return get_state_bar_graph(states)
    # Sector Analytic
    elif data_domain == SEARCH_DATA_DOMAIN_RECORD:
        orgs_raw = sqs.facet_counts().get('fields', {}).get('sector_id', [])
        orgs = \
            [(ORG_TYPE_SECTOR_MAPPING.get(i[0], 'Unknown'), i[1]) for i in orgs_raw if i[1] > 0]
        return get_sector_analytics(orgs)
    # Not Supported
    else:
        _log.error('Search Data Domain: %s is not supported' %data_domain)


def retrieve_params_from_session(request, form_type):
    params = None

    try:
        search_type = request.session.pop('search_form_type')
        url_params = request.session.pop('search_form_data')

        if search_type == form_type:
            params = QueryDict(url_params)
    except:
        return params

    return params

def extract_industry_from_industries(params):
    # Populate the industry field so the adv search industry checkboxes will pre-populate
    industries = params.getlist('industries')
    industry_ids = None

    if industries is not None:
        # For Comma Separated Entries
        if len(industries) == 1:
            industry_ids = industries[0].split(',')
        else:
            industry_ids = industries

        industry_ids = [i for i in industry_ids if i != '']

        if industry_ids and len(industry_ids) > 0:
            industry = Industry.objects.filter(id__in = industry_ids)
            if industry:
                params['industry'] = industry

    return params


def is_paginate(search_form):
    if search_form.cleaned_data['paginate']:
        return search_form.cleaned_data['paginate']
    else:
        if search_form.cleaned_data['page_type'] == 'overview':
            return False
        else:
            return True


def calculate_results_per_page(search_form):
    if search_form.cleaned_data['rpp'] > 0:
        return search_form.cleaned_data['rpp']
    else:
        #defaults
        if search_form.cleaned_data['page_type'] == 'overview':
            return GOVINI_SEARCH_OVERVIEW_RPP
        else:
            return GOVINI_SEARCH_RPP


def get_user_search_preferences(request):
    p = get_user_default_filters(request.user)
    state = p.get('location_full', None)
    industries = p.get('industries_full', None)

    # Append any preferences the user has set
    prefs = {}
    if industries and state:
        prefs = {'state':state, 'industry':industries, 'state_abbrv': state.name}
    elif state:
        prefs = {'state':state, 'state_abbrv': state.name}
    elif industries:
        prefs = {'industry':industries}


    return prefs

def term_autocomplete_list_return(queryset, num, type):

    terms = []
    if 'naics_code' in type or 'fsc_code' in type:
        terms = [{ "id": term.external_id,
                   "value": term.external_id,
                   "label": term.name} for term in queryset[:num]]
    elif 'state' in type:
        terms = [{ "id": term.name,
                   "value": term.name,
                   "label": "%s (%s)" % (term.display_name, term.name)} for term in queryset[:num]]
    elif 'county' in type:
        terms = [{ "id": term.external_id,
                   "value": term.external_id,
                   "label": term.name} for term in queryset[:num]]
    elif 'nigp_code' in type:
        terms = [{ "id": term.external_id,
                   "value": term.external_id.split(":")[-1],
                   "label": term.name} for term in queryset[:num]]
    elif 'cfda_code' in type:
        terms = [{ "id": term.number,
                   "value": term.number,
                   "label": "(%s) %s" %(term.number, term.title)} for term in queryset[:num]]
    else:
        _log.error('Autocomplete for Type=%s Not Supported' %type)

    if len(terms) == 0:
        return HttpResponse('[]')

    return HttpResponse(content=json.dumps(terms, indent=4), mimetype='charset=utf8')


def get_person_or_org(term, org_or_person):
    sqs = []
    if org_or_person == 'org':
        sqs = SearchQuerySet().filter(search_data_domain=SEARCH_DATA_DOMAIN_ORG).filter(title_icontains=term).order_by('title')
    else:
        sqs = SearchQuerySet().filter(search_data_domain=SEARCH_DATA_DOMAIN_PEOPLE).filter(fname=term).order_by('fname')
    return sqs

def term_autocomplete(request):

    term = request.GET.get('term', 'a').lower()
    type = request.GET.get('type', '')
    state = request.GET.get('state','')
    qs = []

    if 'naics_code' in type:
        qs = Term.objects.naics_codes_autocomplete(term).order_by('name')
    elif 'fsc_code' in type:
        qs = Term.objects.fsc_codes_autocomplete(term).order_by('name')
    elif 'nigp_code' in type:
        qs = Term.objects.nigp_codes_autocomplete(term).order_by('name')
    elif 'state' in type:
        qs = GeographyState.objects.states_autocomplete(term).order_by('name')
    elif 'cfda_code' in type:
        qs = CFDAProgramView.objects.cfda_codes_autocomplete(term).order_by('title')
    elif 'county' in type:
        if state:
            state_id = GeographyState.objects.get(name = state.upper())
            qs = GeographyCounty.objects.counties_autocomplete(term,state_id).order_by('name')
    else:
        _log.error('Autocomplete for Type=%s Not Supported' %type)

    return term_autocomplete_list_return(qs, 10, type)

def update_params(params):
    naics_code_autocomplete = params.getlist('adv-naics_code_autocomplete')
    params.setlist('adv-naics_code', naics_code_autocomplete)

    fsc_code_autocomplete = params.getlist('adv-fsc_code_autocomplete')
    params.setlist('adv-fsc_code', fsc_code_autocomplete)

    nigp_code_autocomplete = params.getlist('adv-nigp_code_autocomplete')
    for i,v in enumerate(nigp_code_autocomplete):
        nigp_code_autocomplete[i] = 'NIGP:' + v
    params.setlist('adv-nigp_code', nigp_code_autocomplete)

    state_autocomplete = params.getlist('adv-state_autocomplete')
    params.setlist('adv-state', state_autocomplete)

    cfda_code_autocomplete = params.getlist('adv-cfda_code_autocomplete')
    params.setlist('adv-cfda_code', cfda_code_autocomplete)

    county_autocomplete = params.getlist('adv-county_autocomplete')

    external_id = []
    county_names = ''
    ex_id = 0
    if len(state_autocomplete) == 1:
        state = state_autocomplete[0]
        state_id = (GeographyState.objects.get(name=state)).id

        for county in county_autocomplete:

            try:
                geo_county = GeographyCounty.objects.get(name=county, state=state_id)
                ex_id = geo_county.external_id
                name = geo_county.name
            except:
                try:
                    geo_county = GeographyCounty.objects.get(external_id=county, state=state_id)
                    ex_id = geo_county.external_id
                    name = geo_county.name
                except:
                    pass

            if ex_id and name:
                external_id.append(ex_id)
                if county_names:
                    county_names += ',' + name
                else:
                    county_names = name

    else:
        pass

    params.setlist('adv-county', external_id)
    params.__setitem__('adv-county_names', county_names)

    no_amount = params.get('no_amount')
    if  not no_amount:
        params['no_amount'] = 'False'

''' Save Search '''
def save_search_check_exists(request, name):
    name = name.strip()
    check_save_search = GoviniSavedSearch.objects.filter(name=name, user=request.user, visible=True)
    existing = "false" if check_save_search.count() == 0 else "true"
    return HttpResponse(existing)

def save_search_popup_reset(request, _id):
    try:
        save_searches = GoviniSavedSearch.objects.get(id=_id, user=request.user, visible=True)
    except: 
        pass
    url = ''
    if save_searches:
        url = save_searches.get_absolute_url()
    return HttpResponse(url)

@render_to('search/snippets/save_search_prompt.html')
def save_search_query(request):
    user = request.user
    search_form_data = request.GET.copy()
    save_search_id = search_form_data.get('adv-save_search_id', None)
    save_search_name = ''
    url = ''
    domain = search_form_data.get('domain', SEARCH_DATA_DOMAIN_RECORD)
    existing = False
    
    # Update/Create an entry on the govini_saved_search
    # Update
    if save_search_id:
        update_params(search_form_data)
        search_form = get_form_for_domain(int(domain))(search_form_data, user=request.user, prefix='adv', page_type='advance')
        if search_form.is_valid():
            save_search = GoviniSavedSearch.objects.get(id=save_search_id)
            save_search.search_form_data = search_form.cleaned_data
            save_search.save()
            save_search_id = save_search.id
            save_search_name = save_search.name
            url = save_search.get_absolute_url()
            ds = 'domain='
            index = url.find('domain') + ds.__len__()
            if url[index] == '&':
                save_search.content_type = domain
                save_search.save()
        # TODO: Return Errors

    #Create
    else:
        save_search_name = search_form_data.get('save_search_name')
        update_params(search_form_data)
        search_form = get_form_for_domain(int(domain))(search_form_data, user=request.user)
        if search_form.is_valid():
            save_search = GoviniSavedSearch.objects.create(name = save_search_name,
                                                           user = user,
                                                           search_form_data = search_form.cleaned_data,
                                                           content_type = int(domain))
            save_search_id = save_search.id
            save_search_name = save_search.name
            url = save_search.get_absolute_url()
    return {
        'save_search_id': save_search_id,
        'save_search_name' : save_search_name,
        'url' : url,
        'existing': existing,
    }

@render_to('')
def search_ajax(request, search_data_domain, data_url):
    show_analytics = False
    chart = None
    paginator = []
    paginate = False

    # Search Request
    qp = QueryParser()
    q = request.GET.get('q')
    
    params = qp.convert_to_query(request.GET.copy(), q)
    search_form = get_form_for_domain(search_data_domain)(params, user=request.user)

    # Return the Search results with pagination
    if search_form.is_valid():
        sqs = search_form.get_query()

        # Create a control based on the params
        control = create_control_query(params)
        control_form = get_form_for_domain(search_data_domain)(control, user=request.user)

        if control_form.is_valid():
            control_sqs = control_form.get_query()

            # Paginate Results
            paginate = is_paginate(search_form)
            rpp = calculate_results_per_page(search_form)

            paginator = get_paginated_results(sqs, request, rpp)

            if show_analytics:
                chart = get_analytics_for_domain(sqs, control_sqs, search_data_domain)

    else:
        paginator =  get_fake_paginator(0, 0, 1)
        paginate = False
        show_analytics = False

    response = {
        'results_paginator': paginator,
        'max_score': sqs.max_score(),
        'paginate': paginate,
        'chart': chart,
        'show_analytics': show_analytics
    }

    # Redirect to the right page based on the data_url
    return response, data_url

def remove_items_from_dict(fields, dict):
    for field in fields:
        if dict.__contains__(field):
            dict.pop(field)

    return dict

def create_control_query(params):
    fields = ['none_of_these_words', 'exact_phrase', 'any_of_these_words']
    # Clear out Q,
    control = params.copy()
    control.__setitem__('q','*:*')

    control = remove_items_from_dict(fields, control)

    return control


def quarters_range(date_to, date_from=None):
    result = []
    if date_from is None:
        date_from = datetime.now()
    quarter_to = (date_to.month/4)+1
    for year in range(date_from.year, date_to.year+1):
        for quarter in range(1, 5):
            if date_from.year == year and quarter <= quarter_to:
                continue
            if date_to.year == year and quarter > quarter_to:
                break
            result.append([quarter, year])
    return [datetime(i[1],i[0]*3-2, 1) for i in result]


@render_to('')
def search(request, search_data_domain, data_url, ajax_url):

    # For filtering, we will need to hide the following fields from the form
    fields_to_hide = ('q', 'state', 'state_abbrv', 'naics_code', 'fsc_code', 'nigp_code', 'cfda_code', 'start_amount', 'end_amount', 'city', 'county', 'industries', 'start_date', 'end_date', 'industry', 'place_of_performance', 'sector', 'last_name', 'first_name', 'none_of_these_words', 'exact_phrase', 'element_status', 'procurement_status', 'grant_status', 'no_amount', 'any_of_these_words', 'county_names', 'wo_elements', 'current_status_only', 'org_id', 'person_id')
    domain_facet = {}
    charts = {}
    entity_id = None
    quarters = []
    if len(request.GET) > 0:
        # Retrieve the Form based on the domain
        # Quick Search
        qp = QueryParser()
        q = request.GET.get('q')
        params = qp.convert_to_query(request.GET.copy(), q)
        
        #TODO: Hack. Fix Later
        if 'no_amount' not in params:
            params['no_amount'] = True
        search_form = get_form_for_domain(search_data_domain)(params, fields_to_hide=fields_to_hide, user=request.user, page_type='results')
        _log.debug('Search Form Data = %s' % search_form.data)

        # For Overview and Advance Search, we will need to run the query and return the results and facets
        if  search_form.is_valid():
            sqs = search_form.get_query()
            quarters = quarters_range(search_form._default_query_fields.get('maxDate'),
                                      search_form._default_query_fields.get('minDate'))

            # Create a control based on the params
            control = create_control_query(params)
            control_form = get_form_for_domain(search_data_domain)(control, fields_to_hide=fields_to_hide, user=request.user, page_type='results')

            if control_form.is_valid():
                control_sqs = control_form.get_query()
                buyer_seller_results = sqs.facet('buyer_relevance_profile').facet('seller_relevance_profile')
                if search_data_domain == 3:
                    buyer_table, buyer_table_avg = get_fomrated_table(buyer_seller_results.facet_counts()['fields']['buyer_relevance_profile'])
                    seller_table, seller_table_avg = get_fomrated_table(buyer_seller_results.facet_counts()['fields']['seller_relevance_profile'])
                else:
                    buyer_table = []
                    buyer_table_avg = []
                    seller_table = []
                    seller_table_avg = []

                # log query
                tasks.log_query.delay(q, request.user, search_data_domain)

                # Results Per Page
                paginate = is_paginate(search_form)
                rpp = calculate_results_per_page(search_form)

                # Facets
                sqs = sqs.facet('sector_id').facet('loc_state')
                domain = request.GET.get('domain', '1')
                qp = QueryParser()
                q = request.GET.get('q')
                params = qp.convert_to_query(request.GET.copy(), q)

                new_search_form = get_form_for_domain_facet()(params, user=request.user)
                domain_facet = get_domain_facet(new_search_form, request.user, search_data_domain)
                paginator = get_paginated_results(sqs, request, rpp)
                charts = get_query_analytics(sqs, control_sqs, search_data_domain)

        else:
            # For errors, no results will be displayed with empty charts
            _log.error('Search: Form is not valid. Error = %s' % search_form.errors)

            paginator = get_fake_paginator(0, 0, 1)
            paginate = False
            charts = {
                'sector_chart': get_sector_analytics([]),
                'sector_chart_bar': get_sector_analytics_bar([]),
                'state_chart': get_state_bar_graph([])
            }

        try:
            max_score = sqs.max_score()
        except:
            max_score = 1

        response = {
                    'search_form': search_form,
                    'max_score': max_score,
                    'results_paginator': paginator,
                    'paginate': paginate,
                    'search_data_domain': search_data_domain,
                    'ajax_url': ajax_url,
                    'quarters': quarters,
                    'domain_facet': domain_facet,
                    'domain': "%s" % search_data_domain,
            }

        # Append the charts to the response
        response.update(charts)

        return response, data_url


    else:
        # Redirect back to the Home Page
        return redirect(default_view)


def get_domain_facet(search_form, user, data_domain):
    domain_facet = {'orgs': 0, 'people': 0, 'solicitation': 0}

    # For data domain specific facets, we will need to run the query and not restrict the queryset
    if search_form.is_valid():
        data_domain_facet = search_form.get_query().facet('search_data_domain').facet_counts()
        data_domain_facet = data_domain_facet.get('fields').get('search_data_domain')
        #import pdb;pdb.set_trace()

        # Convert to dic to make it easier to displayed
        for key, value in data_domain_facet:
            type = int(key)
            if type == SEARCH_DATA_DOMAIN_ORG:
                domain_facet.update({'orgs': value})
            elif type == SEARCH_DATA_DOMAIN_PEOPLE:
                domain_facet.update({'people': value})
            elif type == SEARCH_DATA_DOMAIN_RECORD:
                domain_facet.update({'solicitation': value})

        _log.debug('data_domain_facet = %s' % data_domain_facet)
    else:
        _log.error('Search: Form is not valid. Error = %s' % search_form.errors)

    _log.debug('domain_facet = %s' % domain_facet)


    return domain_facet


@render_to('search/overview/navigation_bar.html')
def domain_facet(request):

    domain = request.GET.get('domain', '1')
    qp = QueryParser()
    q = request.GET.get('q')
    params = qp.convert_to_query(request.GET.copy(), q)
    search_form = get_form_for_domain(int(domain))(params, user=request.user)
    domain_facet = get_domain_facet(search_form, request.user, domain)

    return {
        'domain': "%s" % domain,
        'domain_facet': domain_facet
    }

def set_autocomplete(params):
    naics_code = params.getlist('naics_code')
    params.setlist('naics_code', [",".join(naics_code)])

    fsc_code = params.getlist('fsc_code')
    params.setlist('fsc_code', [",".join(fsc_code)])

    nigp_code = params.getlist('nigp_code')
    params.setlist('nigp_code', [",".join(nigp_code)])

    cfda_code = params.getlist('cfda_code')
    params.setlist('cfda_code', [",".join(cfda_code)])

    state = params.getlist('state')
    params.setlist('state', [",".join(state)])

    county = params.getlist('county')
    params.setlist('county', [",".join(county)])
    
    org_id = params.getlist('org_id')
    params.setlist('org_id', [",".join(org_id)])
    
    person_id = params.getlist('person_id')
    params.setlist('person_id', [",".join(person_id)])



@login_required
def adv_search(request, search_data_domain, data_url, redirect_url, popup_url):

    fields_to_hide = ('place_of_performance')

    # For Silver Users and above
    if request.user.govini_profile.get().is_paid_subscriber():

        # Save Search / Search Popup
        if len(request.GET) > 0:
            #Prepare to reload
            params=request.GET.copy()
            
            # TODO: Fix hacks for state and industry
            state_abbrv = params.get('state_abbrv', None)
            if state_abbrv:
                params['state'] = state_abbrv

            try:
                no_amount = params['no_amount']
            except:
                no_amount = None
            if not no_amount or no_amount == 'True':
                params['no_amount'] = True
            elif no_amount == 'False':
                params['no_amount'] = False
                
            try:
                current_status_only = params['current_status_only']
            except:
                current_status_only = None
            if not current_status_only or current_status_only == 'False':
                params['current_status_only'] = False
            elif current_status_only == 'True':
                params['current_status_only'] = True

            sector=params.getlist('sector')

            element_status = params.getlist('element_status')
            procurement_status = get_procurement_from_element(element_status)
            grant_status = get_grant_from_element(element_status)              

            industry = params.getlist('industry')
            set_autocomplete(params)

            try:
                if procurement_status:
                    del params['procurement_status']
            except:
                pass
            try:
                if grant_status:
                    del params['grant_status']
            except:
                pass
            if element_status:
                del params['element_status']
            if sector:
                del params['sector']
            if industry:
                del params['industry']
            else:
                params = extract_industry_from_industries(params)
            

            search_form = get_form_for_domain(search_data_domain)(initial=params, fields_to_hide=fields_to_hide,
                                                                   user=request.user, page_type='advance',
                                                                   prefix='adv', sector=sector, procurement_status = procurement_status,
                                                                   grant_status=grant_status, element_status=element_status, 
                                                                   industry=industry)

        #Validate Advance Search
        elif len(request.POST) > 0:
            params = request.POST.copy()
            update_params(params)
            search_form = get_form_for_domain(search_data_domain)(params, user=request.user, fields_to_hide=fields_to_hide, page_type='advance', prefix='adv')
            #Redirect to Search
            if search_form.is_valid():
                url_params = search_form.data.urlencode()
                url_params = convert_to_url(search_form.cleaned_data)
                _log.debug('Cleaned Data URL Encoding = %s' %url_params)

                # Cache Form data for IE
                browser = request.META['HTTP_USER_AGENT']
                if browser.find('MSIE') > 0:
                    request.session['search_form_type'] = SEARCH_DATA_DOMAIN_PEOPLE
                    request.session['search_form_data'] = url_params

                search_url = '%s?%s' %(redirect_url, url_params)

                return redirect(search_url)
            #Return the form with errors
            else:
                _log.error('Advance Search: Form is not valid. Error = %s' %search_form.errors)
        # New Form
        else:
            # IE Back Button Workaround
            browser = request.META['HTTP_USER_AGENT']
            if browser.find('MSIE') > 0:
                # Retrieve form Variables from session
                params = retrieve_params_from_session(request, SEARCH_DATA_DOMAIN_PEOPLE)

                if params:
                    search_form = get_form_for_domain(search_data_domain)(params, fields_to_hide=fields_to_hide, user=request.user, page_type='advance', prefix='adv')
                else:
                    # Create a new form
                    search_form = get_form_for_domain(search_data_domain)(fields_to_hide=fields_to_hide, user=request.user, page_type='advance', prefix='adv')
            # Create a new form
            else:
                search_form = get_form_for_domain(search_data_domain)(fields_to_hide=fields_to_hide, user=request.user, page_type='advance', prefix='adv')

        #Return to original form
        response = {
            'adv_search_form': search_form,
        }
        
        # Ajax Request
        if request.is_ajax():            
            return render_to_response(popup_url, response, context_instance=RequestContext(request))
        else:
            return render_to_response(data_url, response, context_instance=RequestContext(request))
    
    #Redirect to Home Page
    else:
        return redirect(default_view)


@render_to('search/snippets/terms.html')
def get_term_children(request):

    children = []

    if(request.GET.get('id')):
        term = Term.objects.get(id=request.GET.get('id'))
        children = term.children.order_by('display_label')

    return {
        'terms': children
    }

@login_required
@csrf_exempt
def notify_saved_search(request, save_search_id):
    saved_search = get_object_or_404(GoviniSavedSearch, id=save_search_id, user=request.user)

    if saved_search:
        notify = saved_search.notify_results
        if notify:
            saved_search.notify_results = False
        else:
            saved_search.notify_results = True

        saved_search.save()

    return HttpResponse(saved_search.notify_results)


@login_required
@csrf_exempt
@render_to('search/saved_search_row.html')
def rename_saved_search(request, search_id):

    saved_search = get_object_or_404(GoviniSavedSearch, id=search_id, user=request.user)

    if request.POST:
        renamed = request.POST.get('renamed', '')
        saved_search.name = renamed
        saved_search.search_form_data.update({'save_search_name': renamed})
        saved_search.save()

    return {'saved_search': saved_search}


@render_to('search/saved_search.html')
@login_required
def saved_searches(request):

    saved_searches = GoviniSavedSearch.objects.filter(user = request.user, visible=True)

    if request.POST:
        saved_search_list = request.POST.getlist('saved_search_select')
        delete_saved_searches = saved_searches.in_bulk(saved_search_list).values()
        for delete_saved_search in delete_saved_searches:
            delete_saved_search.visible = False
            delete_saved_search.save()
    return {'saved_searches': saved_searches }

def get_saved_searches(request):
    saved_searches = GoviniSavedSearch.objects.filter(user = request.user, visible=True)
    saved_searches = sorted(saved_searches, key=attrgetter('date_modified'), reverse=True)
    return saved_searches

@render_to('search/feed/saved_search.html')
@login_required
def saved_search_feed(request):
    saved_searches = get_saved_searches(request)
    count = len(saved_searches)
    saved_searches = saved_searches[:5]
    return {'saved_searches': saved_searches, 'count': count}


@render_to('search/feed/saved_search.html')
@login_required
def view_all(request):
    saved_searches = get_saved_searches(request)
    return {'saved_searches': saved_searches}


@render_to('search/analytics/detail_analytics.html')
def search_details_analytics(request, search_data_domain=2):
    if len(request.GET) > 0:
        domain = request.GET.get('domain', '2')

        form = get_form_for_domain(int(domain))(request.GET, user=request.user)
        if form.is_valid():
            sqs = form.get_query()
            sqs = sqs.facet('sector_id').facet('loc_state')
            buyer_seller_results = sqs.facet('buyer_relevance_profile').facet('seller_relevance_profile')
            if int(search_data_domain) == 3:
                buyer_table, buyer_table_avg = get_fomrated_table(buyer_seller_results.facet_counts()['fields']['buyer_relevance_profile'])
                seller_table, seller_table_avg = get_fomrated_table(buyer_seller_results.facet_counts()['fields']['seller_relevance_profile'])
            else:
                buyer_table = []
                buyer_table_avg = []
                seller_table = []
                seller_table_avg = []

            # Create a control based on the params
            control = create_control_query(request.GET)
            control_form = get_form_for_domain(search_data_domain)(control, user=request.user, page_type='results')

            if control_form.is_valid():
                control_sqs = control_form.get_query()
                response_dict = get_query_analytics(sqs, control_sqs, search_data_domain=int(search_data_domain))
                response_dict['search_data_domain'] = int(domain)
                response_dict['buyer_table'] = buyer_table
                response_dict['seller_table'] = seller_table
                response_dict['buyer_table_avg'] = buyer_table_avg
                response_dict['seller_table_avg'] = seller_table_avg

                return response_dict

    return {}


@render_to('search/analytics/element_ajax_analytics.html')
def search_element_analytics(request):

    if len(request.GET) > 0:
        domain = request.GET.get('domain', '2')

        form = get_form_for_domain(int(domain))(request.GET, user=request.user)
        if form.is_valid():
            sqs = form.get_query()
            sqs = sqs.facet('sector_id').facet('loc_state')
            pp = True if form['show_element_industry_analytics_bool'].value() == 'true' else False

            industry_list = str(form['industries'].value()).split(',')
            status_list = form.cleaned_data['element_status']

            return get_query_element_analytics(sqs, show_industry=pp, industry_list=industry_list, status_list=status_list)

    return {}


@render_to('search/analytics/element_ajax_analytics_candle.html')
def search_element_analytics_candle(request):

    if len(request.GET) > 0:
        domain = request.GET.get('domain', '2')

        form = get_form_for_domain(int(domain))(request.GET, user=request.user)
        if form.is_valid():
            sqs = form.get_query()
            pp = False if form['show_element_cycle_analytics_bool'].value() == 'false' else True

            return get_query_element_chart(sqs, request, show_cycle_time=pp)

    return {}
