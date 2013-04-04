from django import forms
from govini.govrefdata.models import Industry, GeographyState, GeographyCounty
from govini.govrecordprograms.models import CFDAProgramView
from poplicus.baseref.models import Term, GeoTerm
from poplicus.baseref.managers import TermManager
from django.contrib.localflavor.us.forms import USStateSelect, USStateField, USZipCodeField
from django.utils.datastructures import MultiValueDict, MergeDict
from .models import GoviniUserSearchPreferences, get_user_default_filters
from govini.search import UNKNOWN_INDUSTRY, SEARCH_DATA_DOMAIN_ALL, SEARCH_DATA_DOMAIN_RECORD, SEARCH_DATA_DOMAIN_ORG,\
                          SEARCH_DATA_DOMAIN_PEOPLE, SEARCH_DATA_DOMAIN_DOCUMENT, SEARCH_SORT_ELEMENT, SEARCH_SORT_ORG,\
                          SEARCH_SORT_PEOPLE,SEARCH_SORT, SEARCH_SORT_RELEVANCE, SEARCH_SORT_DATE, SEARCH_SORT_NAME, \
                          SEARCH_SORT_AMOUNT, SEARCH_SORT_ELEMENT, SEARCH_SORT_SECTOR, SEARCH_SORT_FOR_ELEMENT, NUM_ELEMENT_TYPES, \
                          NUM_INDUSTRIES
from govini.search.govini_solr_backend import SearchQuerySet, AmountQuery
from haystack.backends import SQ
from django.forms.util import flatatt
from django.core.urlresolvers import reverse
from django.utils.safestring import mark_safe
from django.utils.encoding import smart_unicode, force_unicode
import re
from datetime import datetime, date, time
from django.core.exceptions import ValidationError
from poplicus.baseref.constants import ORG_TYPE_SECTOR_MAPPING, ORG_TYPE_MAPPING, GRANT_RECORDS_MAPPING, SOLICITATION_RECORDS_STATES
from operator import itemgetter
from opencrowd.cab.coreapp import get_log
import json

_log = get_log(__name__)


def is_number(value):
    try:
        float(value)
        return True
    except ValueError:
        return False


class HorizRadioRenderer(forms.RadioSelect.renderer):
    def render(self):
            return mark_safe(u'\n'.join([u'%s\n' % w for w in self]))


class TermAutoCompleteTextWidget(forms.MultipleHiddenInput):

    def render_autocomplete(self, name, value, attrs=None):

        if attrs is None:
            attrs = {}

        if attrs.get('id', None) is None:
            attrs['id'] = 'id_%s' % name

        if attrs.get('size'):
            del attrs['size']

        hidden_id = attrs.get('id')
        autocomplete_id = '%s_autocomplete' % hidden_id
        attrs['id'] = autocomplete_id

        auto_final_attrs = self.build_attrs(attrs, type='text', name='%s_autocomplete' % name)

        if auto_final_attrs.get('size'):
            del auto_final_attrs['size']

        if value != '':
            if isinstance(value, basestring):
                value = value.split(',')

        # Determine the right value to store based on the type 
        auto_final_attrs['value'] = force_unicode(self._format_value(value))
        tags = []
        if value:
            for i in value:
                if 'naics_code' in name or 'fsc_code' in name or 'nigp_code' in name:
                    try:
                        term = Term.objects.get(external_id=i)
                        if 'nigp_code' in name:
                            tags.append(term.external_id.split(":")[-1])
                        else:
                            tags.append(term.external_id)
                    except:
                        pass
                elif 'cfda_code' in name:
                    try:
                        term = CFDAProgramView.objects.get(number=i)
                        tags.append(term.number)
                    except:
                        pass
                elif 'state' in name:
                    try:
                        state = GeographyState.objects.get(name=i)
                        tags.append(state.name)
                    except:
                        pass
                elif 'county' in name:
                    try:
                        county = GeographyCounty.objects.get(external_id=i)
                        tags.append(county.name)
                    except:
                        pass

        # Store the selected values in the hidden form field
        js = "$('#%s').tagit({\
                    tagSource: '%s?type=%s',\
                    minLength:1,\
                    select:true,\
                    initialTags: %s,\
                    allowNewTags: false, \
                    tagsChanged: function(tagValue,action,element) {disable_county(tagValue,action,element,'%s');},\
                });" % \
                (autocomplete_id, reverse('govini.search.views.term_autocomplete'), name, json.dumps(tags), name);

        return u"<ul%s /><script type='text/javascript'>%s</script>" % (flatatt(auto_final_attrs), js)


    def render(self, name, value, attrs=None, choices=()):
        if value is None:
            value = ''

        hidden_final_attrs = self.build_attrs(attrs, name=name)

        if value != '':
            # Only add the 'value' attribute if a value is non-empty.
            hidden_final_attrs['value'] = force_unicode(self._format_value(value))

        input = u'<input%s />' % flatatt(hidden_final_attrs)
        js = self.render_autocomplete(name, value, attrs)

        return mark_safe(u'%s%s' % (input, js))


class TermAutoCompleteField(forms.ModelMultipleChoiceField):

    widget = TermAutoCompleteTextWidget


    def __init__(self, queryset=None, hidden=True,
                 required=False, widget=None, label=None, initial=None,
                 help_text=None, to_field_name='external_id', *args, **kwargs):

        if queryset is None:
            queryset = Term.objects.all()

        self.hidden = hidden

        super(TermAutoCompleteField, self).__init__(
            queryset,
            cache_choices=True,
            required=required,
            widget=widget,
            label=label,
            initial=initial,
            help_text=help_text,
            to_field_name=to_field_name,
            *args,
            **kwargs)

    def widget_attrs(self, widget):
        if self.hidden:
            return {'type': 'hidden'}
        return {'type': 'text', 'size': 5}


    def clean(self, value):

        if self.required and not value:
            raise ValidationError(self.error_messages['required'])
        elif not self.required and not value:
            return []
        if not isinstance(value, (list, tuple)):
            raise ValidationError(self.error_messages['list'])
        key = self.to_field_name or 'pk'
        for pk in value:
            try:
                self.queryset.filter(**{key: pk})
            except ValueError:
                pass

        qs = self.queryset.filter(**{'%s__in' % key: value})
        pks = set([force_unicode(getattr(o, key)) for o in qs])

        self.run_validators(value)
        return qs


def get_sector_choices():
    sector_choices = [(x, ORG_TYPE_SECTOR_MAPPING.get('%s' % x)) for x in range(1, 7)]
    sector_choices = sorted(sector_choices, key=itemgetter(1))
    return sector_choices

def get_procurement_choices():
    stypes = Term.objects.solicitation_types()
    choices = [(t.name, t.name) for t in stypes if not t.name == 'Grant-Notices']
    
    return choices

def get_grant_choices():
    names = [GRANT_RECORDS_MAPPING.get('%s' % x) for x in range(1, 5)]
    choices = []
    for n in names:
        choices.append((n, n))
    return choices

def get_element_choices():
    choices_1 = get_grant_choices()
    choices_2 = get_procurement_choices()
    choices = choices_1 + choices_2
    return choices

def get_days_choices():
    return [('5', '5 days'), ('10', '10 days'),('15', '15 days')]

class BaseSearchForm(forms.Form):
    '''Keyword'''
    q = forms.CharField(required=False, max_length=500, label='Keywords')
    
    '''Facet Filters'''
    industry = forms.ModelMultipleChoiceField(queryset=Industry.objects.all(), label='Industry', widget=forms.CheckboxSelectMultiple(attrs={'size': 10, 'class':'industry'}), required=False, initial=Industry.objects.all())
    industries = forms.CharField(required=False, max_length=255)
    start_date = forms.DateTimeField(required=False)
    end_date = forms.DateTimeField(required=False)
    state = TermAutoCompleteField(required=False, to_field_name = 'name')
    state_abbrv = forms.CharField(required=False)
    county = TermAutoCompleteField(required=False, queryset=GeographyCounty.objects.all())
    county_names = forms.CharField(required=False)
    
    '''Configurations'''
    rpp = forms.IntegerField(required=False, widget=forms.HiddenInput)
    paginate = forms.BooleanField(required=False, widget=forms.HiddenInput)
    
    '''Advance Search'''
    naics_code = TermAutoCompleteField(required=False)
    fsc_code = TermAutoCompleteField(required=False)
    nigp_code = TermAutoCompleteField(required=False)
    cfda_code = TermAutoCompleteField(required=False, queryset=CFDAProgramView.objects.all(), to_field_name = 'number')
    start_amount = forms.CharField(required=False, max_length=15)
    end_amount = forms.CharField(required=False, max_length=15)
    no_amount = forms.NullBooleanField(required=False, initial=True, widget=forms.CheckboxInput())
    city = forms.ModelChoiceField(required=False, queryset=Term.objects.all())
    page_type = forms.CharField(required=False, widget=forms.HiddenInput, initial='overview')
    domain = forms.CharField(required=False, widget=forms.HiddenInput, initial='1')
    sector = forms.MultipleChoiceField(required=False, choices=get_sector_choices(), widget=forms.CheckboxSelectMultiple(attrs={'class': 'sector'}), initial=[s[0] for s in get_sector_choices()])
    
    org_id = forms.CharField(required=False, max_length=500, label='Org_id')
    person_id = forms.CharField(required=False, max_length=500, label='Person_id')

    '''element analytics industry/elements'''
    show_element_industry_analytics = forms.CharField(widget=forms.RadioSelect(renderer=HorizRadioRenderer, choices=(('true', 'Industry'), ('false', 'Sector'))), initial='false', required=False)
    show_element_industry_analytics_bool = forms.CharField(required=False, widget=forms.HiddenInput, initial='false')

    show_element_cycle_analytics = forms.CharField(widget=forms.RadioSelect(renderer=HorizRadioRenderer, choices=(('true', 'Cycle time'), ('false', 'Award amount'))), initial='true', required=False)
    show_element_cycle_analytics_bool = forms.CharField(required=False, widget=forms.HiddenInput, initial='true')
    
    show_org_buyer_table = forms.CharField(widget=forms.RadioSelect(renderer=HorizRadioRenderer, choices=(('true', 'Awardee'), ('false', 'Agency'))), initial='true', required=False)
    
    show_award_analytics = forms.CharField(widget=forms.RadioSelect(renderer=HorizRadioRenderer, choices=(('true', 'Agency'), ('false', 'Awardee'))), initial='true', required=False)
    show_award_analytics_bool = forms.CharField(required=False, widget=forms.HiddenInput, initial='true')

    '''Save Search'''
    save_search_id = forms.IntegerField(required=False, widget=forms.HiddenInput)
    save_search_name = forms.CharField(required=False, widget=forms.HiddenInput)

    '''Place of Performance (Solicitation)'''
    place_of_performance = forms.BooleanField(required=False)

    '''Results Filter'''
    sort_by = forms.CharField(required=False, initial=SEARCH_SORT_RELEVANCE, widget=forms.HiddenInput)
    sort_order = forms.CharField(required=False, widget=forms.HiddenInput)
    wo_elements = forms.NullBooleanField(required=False, widget=forms.HiddenInput,  initial=True)

    '''People Fields'''
    first_name = forms.CharField(required=False, max_length=75)
    last_name = forms.CharField(required=False, max_length=75)

    '''Solicitation Fields'''
    exact_phrase = forms.CharField(required=False, max_length=100, label='The exact phrase')
    none_of_these_words = forms.CharField(required=False, max_length=100, label='None of these words')

    element_status = forms.MultipleChoiceField(choices=get_element_choices(),
                                                widget=forms.CheckboxSelectMultiple(attrs={'class': 'element_status'}),
                                            label='Element Types', required=False)

    procurement_status = forms.MultipleChoiceField(choices=get_procurement_choices(),
                                                    widget=forms.CheckboxSelectMultiple(attrs={'class': 'procurement_status'}),
                                                    required=False, initial=[t[0] for t in get_procurement_choices()])

    grant_status = forms.MultipleChoiceField(choices=get_grant_choices(),
                                                widget=forms.CheckboxSelectMultiple(attrs={'class': 'grant_status'}),
                                                required=False, initial=[t[0] for t in get_grant_choices()])
    
    current_status_only = forms.NullBooleanField(required=False, initial=False, widget=forms.CheckboxInput())
    
    '''home page analytics'''
    days_selector = forms.CharField(widget=forms.RadioSelect(renderer=HorizRadioRenderer, choices=get_days_choices()), initial='5', required=False)

    # Since we are using one form for both advance search and filtering results, we will need to control which fields will be shown to the user.
    # fields_to_hide is a list of fields to convert into Hidden Fields
    def __init__(self, data=None, *args, **kwargs):
        # Extract Optional Parameters
        fields_to_hide = kwargs.pop('fields_to_hide', None)
        procurement_status = kwargs.pop('procurement_status', None)
        grant_status = kwargs.pop('grant_status', None)
        element_status = kwargs.pop('element_status', None)  
        sector = kwargs.pop('sector', None)
        industry = kwargs.pop('industry', None)
        page_type = kwargs.pop('page_type', None)
        domain = kwargs.pop('domain', SEARCH_DATA_DOMAIN_ALL)
        wo_elements = kwargs.pop('wo_elements', True)
        
        
        self.user = kwargs.pop('user', None)
        self._default_query_fields = get_user_default_filters(self.user)

        _log.debug('Data = %s' % data)
        
        filtered_data = None
        if data:
            filtered_data = data.copy()
            for key,value in filtered_data.items():
                if not value:
                    filtered_data.pop(key)

        _log.debug('Data (Cleaned) = %s' % filtered_data)

        super(BaseSearchForm, self).__init__(data=filtered_data, *args, **kwargs)

        #When using initial, ModelMultipleChoiceFields do not work via form creation
        if element_status:
            self.fields['element_status'].initial = element_status
            if grant_status or element_status == procurement_status:
                self.fields['grant_status'].initial = grant_status
            if procurement_status or element_status == grant_status:
                self.fields['procurement_status'].initial = procurement_status
        if sector:
            self.fields['sector'].initial = sector
        if industry:
            self.fields['industry'].initial = industry

        # Hide all the fields that are not necessary for this search form
        if fields_to_hide:
            for item in fields_to_hide:
                try:
                    if item in  ('element_status', 'procurement_status', 'grant_status', 'industry', 'sector', 'naics_code', 'fsc_code', 'nigp_code', 'cfda_code', 'place_of_performance', 'state', 'county'):
                        self.fields[item].widget = forms.MultipleHiddenInput()
                    else:
                        self.fields[item].widget = forms.HiddenInput()
                except:
                    pass

        data = self.data.copy()
        data['domain'] = domain

        try:
            if data['wo_elements'] == '':
                data['wo_elements'] = wo_elements
        except:
            pass

        if not 'show_element_industry_analytics' in  data:
            data['show_element_industry_analytics'] = 'false'

        if page_type:
            field_name = 'page_type'
            if self.prefix:
                field_name = self.prefix + '-' + field_name
            data[field_name] = page_type

        self.data = data

    ''' Clean Functions '''
    def clean_q(self):

        q = self.cleaned_data.get('q').strip()         
        # Search Everything
        if q == '*:*':
            q = ''
        # Remove Special Characters from keywords
        else:
            #('Keywords = %s' % q)
            # Extract unrecognized params from q
            quick_search_regex = '[a-zA-Z0-9]+\([a-zA-Z0-9,-. ]+\)|[a-zA-Z0-9]+\(\)|"[a-zA-Z0-9,-. ]+"'

            # Extract the search query parameters and replace them with spaces
            params = re.findall(quick_search_regex, q)
            _log.debug('params = %s' % params)
            for value in params:
                q = q.replace(value, '')
            _log.debug('quick_search_filter = %s' %q)
            sanitized_keywords = re.split('[^a-zA-Z0-9_\-@./: ]', q)
            q = "".join(sanitized_keywords).strip()
            _log.debug('sanitized_filter = %s' %q)

            # Validate only if it not the adv search pages
            page_type = self.data.get('page_type')
            if page_type == 'overview':
                if q is None or len(q) == 0:
                    raise ValidationError('Invalid Keyword')
            #TODO: Fix
            self.data['q'] = q

        return q      

    def clean_start_date(self):
        start_date = self.cleaned_data.get('start_date')

        if not start_date:
            start_date = self._default_query_fields.get('defaultStartDate')
        if start_date < self._default_query_fields.get('minDate'):
            start_date = self._default_query_fields.get('minDate')
        
        # All records are indexed with noon gmt, so make sure this is before
        start_date = datetime.combine(start_date, time(7, 00))
        return start_date

    def clean_end_date(self):
        end_date = self.cleaned_data.get('end_date')
        
        if not end_date:
            end_date = self._default_query_fields.get('maxDate')
        if end_date > self._default_query_fields.get('maxDate'):
            end_date = self._default_query_fields.get('maxDate')

        #All records are indexed with noon gmt, so make sure this is after
        end_date = datetime.combine(end_date, time(13, 00))

        start_date = self.cleaned_data.get('start_date')
        if start_date and end_date:
            if start_date > end_date:
                raise ValidationError('Start date is later than end date')
            
        return end_date

    def clean_start_amount(self):
        # Validate the Amount is a number 
        start_amount = self.cleaned_data.get('start_amount')
        start_amount = re.sub("[\$,]", "", start_amount)

        # Validate
        if start_amount != None and len(start_amount) > 0:
            result = is_number(start_amount)

            if not result:
                raise ValidationError('Invalid Amount')
            return start_amount
        
        # Default Value
        return None

    def clean_end_amount(self):
        end_amount = self.cleaned_data.get('end_amount')
        end_amount = re.sub("[\$,]", "", end_amount)

        # Validate
        if end_amount != None and len(end_amount) > 0:
            result = is_number(end_amount)

            if not result:
                raise ValidationError('Invalid Amount')

            return end_amount
        #Default Value
        return None

    def clean_no_amount(self):
        no_amount = self.cleaned_data.get('no_amount')
        if no_amount == None:
            return True
        return no_amount
    
    def clean_current_status_only(self):
        if self.data.get('adv-current_status_only') == 'on' or self.data.get('current_status_only') == 'True':
            return True
        else:
            return False

    def clean_wo_elements(self):
        wo_elements = self.cleaned_data.get('wo_elements')
        if wo_elements == None:
            return True
        return wo_elements

    def clean_industries(self):
        industries = self.cleaned_data.get('industries')
        if isinstance(industries, (tuple, list)):
            if len(industries) > 0:
                return industries
            industries = ''
        if industries.strip() == '':
            return []
            #industries = ",".join(map(str, Industry.objects.values_list('id', flat=True)))

        return industries.split(',')

    def clean_procurement_status(self):
        self.cleaned_data['element_status'] = list(set(self.cleaned_data.get('element_status', []) + self.cleaned_data.get('procurement_status')))
        return self.cleaned_data.get('procurement_status')
            
    def clean_grant_status(self):
        self.cleaned_data['element_status'] = list(set(self.cleaned_data.get('element_status', []) + self.cleaned_data.get('grant_status')))
        return self.cleaned_data.get('grant_status')       
          

    def _get_base_query(self):
        return SearchQuerySet(using='search_results_node')

    def _get_fields(self):
        return ['status', 'pphone', 'agency_name', 'title', 'published_on', 'max_amount', 'min_amount', 'pemail',
                'lname', 'amount', 'award_amount', 'fname', 'address', 'orgtype', 'population', 'loc_state',
                'loc_city', 'loc_postal_code', 'sdate', 'edate', 'sector', 'num_people',
                'num_records', 'num_gov_orgs', 'num_priv_orgs']

    def get_query(self,
                  start_date=None,
                  end_date=None,
                  include_state=True,
                  include_industries=True,
                  include_all=False):

        if not self.is_valid():
            _log.error(self.errors)
            raise forms.ValidationError('This form is not valid')

        # For Domain Facets, don't filter by domain
        if include_all:
            sqs = SearchQuerySet(using='search_results_node')
        else:
            sqs = self._get_base_query()
        
        # Filter Fields
        fields = self._get_fields()
        sqs = sqs.set_fields(fields)

        if self.cleaned_data.get('q'):
            words = self.cleaned_data['q'].split(' ')
            keyword_query = SearchQuerySet()
            for word in words:
                #Remove spaces
                word = word.strip()
                if word:
                    keyword_query = keyword_query.filter(text__contains=sqs.query.clean(word))
            sqs.query.combine(keyword_query.query)

        #Any
        if self.cleaned_data.get('any_of_these_words'):
            words = self.cleaned_data['any_of_these_words'].split(',')

            any_query = SearchQuerySet()
            for word in words:
                #Remove spaces
                word = word.strip()
                if word:
                    any_query = any_query.filter_or(text__contains=sqs.query.clean(word))
            sqs.query.combine(any_query.query)

        #First do dates, there will always be a date range
        start_date = \
            self.cleaned_data.get('start_date') if not start_date else start_date
        end_date = \
            self.cleaned_data.get('end_date') if not end_date else end_date

        # Date Query
        # Elements
        '''Add a range over edate to restrict results to only elements'''
        date_query = SearchQuerySet()
        element_date_range_query = SearchQuerySet().filter(edate__lt=start_date).filter_or(sdate__gt=end_date)
        element_date_range_query.query.query_filter.negated = True
        date_query.query.combine(element_date_range_query.query)
        date_query.query.combine(element_edate_query.query)

        # People/Orgs
        '''Use Activity Dates as a time filter'''
        #date_query = date_query.filter_or(activity_dates__range=(start_date, end_date))

        #Results filtering on without elements checkbox
        if self.cleaned_data.get('wo_elements') != None:
            wo_elements = self.cleaned_data.get('wo_elements')
            if wo_elements:
                date_query = date_query.filter_or(num_activity__exact=0)

        sqs.query.combine(date_query.query)

        #check amounts
        min_amount = self.cleaned_data.get('start_amount', None)
        max_amount = self.cleaned_data.get('end_amount', None)
        no_amount = self.cleaned_data.get('no_amount', True)

        if min_amount != None or max_amount != None:
            if no_amount:
                amount_query = AmountQuery(min_amount, max_amount)
                sqs.query.combine(amount_query)
            else:
                if min_amount == None:
                #that means theres a max
                    sqs = sqs.filter(award_amount__lte=max_amount)
                elif max_amount == None:
                    #means theres a min
                    sqs = sqs.filter(award_amount__gte=min_amount)
                else:
                    #means theres both
                    sqs = sqs.filter(award_amount__range=(min_amount, max_amount))
        elif not no_amount:
            #if no amount but no range, then only * to *
            sqs = sqs.filter(award_amount__range=('*', '*'))
        else:
            #means want everything
            pass

        #state
        if include_state and self.cleaned_data.get('state'):
            state = self.cleaned_data['state']
            sqs = sqs.filter(loc_state__in=state)

        if include_state and self.cleaned_data.get('state_abbrv'):
            state_abbrv = self.cleaned_data['state_abbrv']
            sqs = sqs.filter(loc_state=state_abbrv)

        #industries
        if include_industries and self.cleaned_data.get('industries'):
            industries = self.cleaned_data['industries']

            if len(industries) > 0 and len(industries) < NUM_INDUSTRIES:
                sqs = sqs.filter(industry_ids__in=industries)

        if include_industries and self.cleaned_data.get('industry'):
            industries = self.cleaned_data['industry']

            if len(industries) > 0 and len(industries) < NUM_INDUSTRIES:
                industries_arr = [industry.id for industry in industries]
                sqs = sqs.filter(industry_ids__in=industries_arr)

        if self.cleaned_data.get('sector'):
            sector = self.cleaned_data['sector']

            if len(sector) > 0 and len(sector) < 6:
                sqs = sqs.filter(sector_id__in=sector)

        # Industry Codes
        if self.cleaned_data.get('naics_code'):
            naics_code = self.cleaned_data['naics_code']
            naics_code_list = [x.external_id for x in naics_code]
            sqs = sqs.filter(naics_codes__in=naics_code_list)

        if self.cleaned_data.get('fsc_code'):
            fsc_code = self.cleaned_data['fsc_code']
            fsc_code_list = [x.external_id for x in fsc_code]
            sqs = sqs.filter(fsc_codes__in=fsc_code_list)

        if self.cleaned_data.get('nigp_code'):
            nigp_code = self.cleaned_data['nigp_code']
            nigp_code_list = [x.external_id for x in nigp_code]
            sqs = sqs.filter(nigp_codes__in=nigp_code_list)

        if self.cleaned_data.get('cfda_code'):
            cfda_code = self.cleaned_data['cfda_code']
            cfda_code_list = [x.number for x in cfda_code]
            sqs = sqs.filter(cfda_codes__in=cfda_code_list)

        if self.cleaned_data.get('county'):
            county = self.cleaned_data['county']
            county_list = [x.external_id for x in county]
            sqs = sqs.filter(loc_county__in=county_list)

        if self.cleaned_data.get('city'):
            sqs = sqs.filter(loc_city=self.cleaned_data['city'])


        #People Filters
        if self.cleaned_data.get('first_name'):
            sqs = sqs.filter(fname=self.cleaned_data['first_name'])

        if self.cleaned_data.get('last_name'):
            sqs = sqs.filter(lname=self.cleaned_data['last_name'])

        
        # Solicitation Filters
        if self.cleaned_data.get('element_status'):
            element_status = self.cleaned_data['element_status']
            current_status_only = self.cleaned_data['current_status_only']
            if (len(element_status) > 0 and len(element_status) < NUM_ELEMENT_TYPES):
                if current_status_only:
                    sqs = sqs.filter(status__in= element_status)
                else:
                    sqs = sqs.filter(project_states__in= element_status)

        if self.cleaned_data.get('exact_phrase'):
            exact_phrase = self.cleaned_data.get('exact_phrase')
            for i in exact_phrase.split(','):
                sqs = sqs.filter(content = i)
            
        if self.cleaned_data.get('none_of_these_words'):
            words = self.cleaned_data['none_of_these_words'].split(' ')
            sqs = sqs.exclude(text__in = words)
        
        if self.cleaned_data.get('org_id'):
            org_id = self.cleaned_data['org_id']
            sqs = sqs.filter(orgs = org_id)
            
        if self.cleaned_data.get('person_id'):
            person_id = self.cleaned_data['person_id']
            sqs = sqs.filter(people = person_id)

        # Results Ordering
        # Highest Score, Latest publish date and title by alphabet
        if self.cleaned_data.get('sort_by'):
            sort_by = self.cleaned_data.get('sort_by')

            if self.cleaned_data.get('sort_order') == 'reverse':
                if len(sort_by.split('-')) > 1:
                    sort_by = sort_by.split('-')[1]
                else:
                    sort_by = '-%s'%sort_by

            sqs = sqs.order_by(sort_by)


        _log.debug('Base SQS Query: %s' %sqs.query)
        return sqs


class OrganizationSearchForm(BaseSearchForm):

    def __init__(self, *args, **kwargs):
        kwargs['domain'] = SEARCH_DATA_DOMAIN_ORG
        super(OrganizationSearchForm, self).__init__(*args, **kwargs)

    def _get_base_query(self):
        return super(OrganizationSearchForm, self)._get_base_query().filter(search_data_domain__exact=SEARCH_DATA_DOMAIN_ORG)

    def _get_fields(self):
        return ['address', 'orgtype', 'sector','award_amount', 'min_amount', 'max_amount', 'title', 'population', 
                'sdate', 'edate', 'buyer_relevance_profile', 'complexity_score', 'num_people', 'num_records', 
                'num_gov_orgs', 'num_priv_orgs']

    def clean(self):
        cleaned_data = super(OrganizationSearchForm, self).clean()

        # Advance Search Validation
        if self.cleaned_data.get('page_type') == 'advance':
            q = self.cleaned_data.get('q')
            
            if q is None or len(q) == 0:
                raise ValidationError('Keywords is required')
            
        return cleaned_data

class PeopleSearchForm(BaseSearchForm):

    def __init__(self, *args, **kwargs):
        kwargs['domain'] = SEARCH_DATA_DOMAIN_PEOPLE
        super(PeopleSearchForm, self).__init__(*args, **kwargs)

    def _get_fields(self):
        return ['fname', 'lname', 'sector', 'title', 'address', 'pphone', 'pemail', 'orgtype', 'award_amount', 'agency_name', 'sdate', 'edate', 'num_people', 'num_records', 
                'num_gov_orgs', 'num_priv_orgs']

    def _get_base_query(self):
        return super(PeopleSearchForm, self)._get_base_query().filter(search_data_domain__exact=SEARCH_DATA_DOMAIN_PEOPLE)

    def clean(self):
        cleaned_data = super(PeopleSearchForm, self).clean()

        # Advance Search Validation
        if self.cleaned_data.get('page_type') == 'advance':
            first_name = self.cleaned_data.get('first_name')
            last_name = self.cleaned_data.get('last_name')
            q = self.cleaned_data.get('q')
            
            if q is None or len(first_name) == 0 and len(last_name) == 0 and len(q) == 0:
                raise ValidationError('One of the fields are required: Keywords, First Name, Last Name')
            
        return cleaned_data


class SolicitationSearchForm(BaseSearchForm):

    def __init__(self, *args, **kwargs):
        kwargs['domain'] = SEARCH_DATA_DOMAIN_RECORD
        super(SolicitationSearchForm, self).__init__(*args, **kwargs)

    def _get_base_query(self):
        return super(SolicitationSearchForm, self)._get_base_query().filter(search_data_domain__exact=SEARCH_DATA_DOMAIN_RECORD)

    def _get_fields(self):
        return ['agency_name', 'address', 'amount','award_amount', 'min_amount', 'max_amount', 'title', 'status', 'published_on', 'sdate', 'edate', 'complexity_score', 'num_people', 'num_records', 
                'num_gov_orgs', 'num_priv_orgs']


    def clean(self):
        cleaned_data = super(SolicitationSearchForm, self).clean()

        # Advance Search Validation
        if self.cleaned_data.get('page_type') == 'advance':
            q = self.cleaned_data.get('q')
            exact_phrase = self.cleaned_data.get('exact_phrase')
            
            if q is None or len(exact_phrase) == 0 and len(q) == 0:
                raise ValidationError('One of the fields are required: Keywords, Exact Phrase')
            
        return cleaned_data


class DocumentSearchForm(BaseSearchForm):

    def __init__(self, *args, **kwargs):
        kwargs['domain'] = SEARCH_DATA_DOMAIN_DOCUMENT
        super(DocumentSearchForm, self).__init__(*args, **kwargs)

    def _get_base_query(self):
        return super(DocumentSearchForm, self)._get_base_query().filter(search_data_domain__exact=SEARCH_DATA_DOMAIN_DOCUMENT)


    def _get_fields(self):
        return ['*']

    def get_query(self, *args, **kwargs):
        sqs = super(DocumentSearchForm, self).get_query(*args, **kwargs)

        if self.cleaned_data.get('exact_phrase'):
            sqs = sqs.filter(content=self.cleaned_data['exact_phrase'])

        if self.cleaned_data.get('none_of_these_words'):
            words = self.cleaned_data['none_of_these_words'].split(' ')
            sqs = sqs.exclude(text__in=words)

        #print ('SQS Query: %s' %(sqs.query))
        return sqs



class SearchPreferencesForm(forms.ModelForm):
    industries = forms.ModelMultipleChoiceField(queryset=Industry.objects.all(), label='Industry(s)', widget=forms.CheckboxSelectMultiple(), required=False)
    location = forms.ModelChoiceField(required=False, queryset=GeographyState.objects.all().order_by('display_name'), empty_label="ALL")

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user')
        initial = {}
        try:
            search_pref = GoviniUserSearchPreferences.objects.get(user=self.user)
            initial.update({'industries': search_pref.industries.all(),
                            'location': search_pref.location })
        except:
            pass

        kwargs['initial'] = initial
        super(SearchPreferencesForm, self).__init__(*args, **kwargs)

    class Meta:
        model = GoviniUserSearchPreferences
        fields = ('industries', 'location')

    def save(self):
        cd = self.cleaned_data

        search_pref, _created = GoviniUserSearchPreferences.objects.get_or_create(user=self.user)
        search_pref.industries = cd.get('industries')
        search_pref.location = cd.get('location')

        search_pref.save()





SEARCH_DATA_DOMAIN_FORMS = {SEARCH_DATA_DOMAIN_ALL: BaseSearchForm,
                            SEARCH_DATA_DOMAIN_RECORD: SolicitationSearchForm,
                            SEARCH_DATA_DOMAIN_ORG: OrganizationSearchForm,
                            SEARCH_DATA_DOMAIN_PEOPLE: PeopleSearchForm,
                            SEARCH_DATA_DOMAIN_DOCUMENT: DocumentSearchForm}


def get_form_for_domain(domain):
    return SEARCH_DATA_DOMAIN_FORMS.get(int(domain))

