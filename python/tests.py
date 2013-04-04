from django.utils import unittest
from django.test.client import Client
from django.conf import settings
from django.utils.importlib import import_module
from django.contrib.auth.models import User
from govini.profiles.models import GoviniProfile
from django.http import QueryDict
from datetime import datetime, date, time, timedelta
from govini.govrefdata.models import Industry
from poplicus.baseref.models import Term
from poplicus.baseref.constants import ORG_TYPE_MAPPING, ORG_TYPE_SECTOR_MAPPING
from operator import itemgetter
from django.utils.encoding import smart_unicode, force_unicode
from govini.search.models import GoviniSavedSearch
import random

class SearchTestCase(unittest.TestCase):
    # Reference 
    # Sample Post
    # response = c.post('/login/', {'username': 'john', 'password': 'smith'})

    # Sample Get
    # response = c.get('/customer/details/')
    @classmethod
    def setUpClass(cls):
        ''' 
        Prerequisites        
        1. Add this config to your popstore db configuration: 
              'BYPASS_CREATION':'yes'.  
        This will stop Django from creating a test popstore db.
        2. Add the following config to your database.py: 
              TEST_RUNNER = 'poplicus.baseref.test_utils.ByPassableDBDjangoTestSuiteRunner'
              
        To execute the tests run the following comand: python manage.py test <app_name> via command line
        '''
        
        # Create Test Users
        #User 1 - Silver
        django_user = User()
        django_user.username = 'ted'
        django_user.password='sha1$26fb9$292b455284ec9e24595afd34a3b8eb46796d5601' #md5 hash
        django_user.first_name = 'Ted'
        django_user.last_name = 'Smith'
        django_user.email = 'tsmith@opencrowd.com'
        django_user.save()
        
        govini_user = GoviniProfile()
        govini_user.user = django_user
        govini_user.user_type = 'silver'
        govini_user.save()
        
        #User 2 - Bronze
        django_user = User()
        django_user.username = 'john'
        django_user.password='sha1$26fb9$292b455284ec9e24595afd34a3b8eb46796d5601' #md5 hash
        django_user.first_name = 'John'
        django_user.last_name = 'Smith'
        django_user.email = 'jsmith@opencrowd.com'
        django_user.save()
        
        govini_user = GoviniProfile()
        govini_user.user = django_user
        govini_user.user_type = 'bronze'
        govini_user.save()
        
    def setUp(self):
        # Every test needs a client.        
        self.client = Client()

    def url_encode_params(self, dict):
        params = QueryDict(None).copy()
        params.update(dict)
        return params.urlencode()
    
    def init_adv_search_params(self):
        
        industries = []
        for industry in Industry.objects.all():
            enable = random.choice([True, False])
            if enable:
                industries.append(industry)
        
        
        element_types = []
        for type in Term.objects.solicitation_types():
            enable = random.choice([True, False])
            if enable:
                element_types.append(type.name)        
            
               
        params = {'adv-q':'system',
               'adv-industry': industries, 
               'adv-sector':self.get_sector_choices(), 
               'adv-element_status':element_types, 
               'adv-start_date':date.today() - timedelta(days=90),
               'adv-end_date': date.today(), 
               'adv-no_amount':True
               }
        
        return params


    def get_sector_choices(self):
        sector_choices = [x for x in range(1, 7)]
        sector_choices = sorted(sector_choices)
        return sector_choices
    
    def convert_to_unicode(self, list):
        list_unicode =[]
        for i in range(0,len(list)):
            list_unicode.append(force_unicode(list[i]))
            
        return list_unicode
    
    def assertEqual_org(self, data, q, start_date, end_date, start_amount, end_amount, no_amount, industry, sector, naics_code, 
                    fsc_code, state, county):
        self.assertEqual(q, data.get('q').strip())
        self.assertEqual(start_date, data.get('start_date'))
        self.assertEqual(end_date, data.get('end_date'))
        self.assertEqual(start_amount, data.get('start_amount'))
        self.assertEqual(end_amount, data.get('end_amount'))
        self.assertEqual(no_amount, data.get('no_amount'))
        self.assertEqual(industry, data.getlist('industry'))        
        self.assertEqual(sector, data.getlist('sector'))
        self.assertEqual(naics_code, data.getlist('naics_code'))
        self.assertEqual(fsc_code, data.getlist('fsc_code'))
        self.assertEqual(state, data.getlist('state'))
        self.assertEqual(county, data.getlist('county'))
    
    def assertEqual_element(self, data, q, exact_phrase, none_phrase, start_date, end_date, start_amount, end_amount, no_amount, industry, 
                    sector, naics_code, fsc_code, state, county, element_status):
        self.assertEqual(exact_phrase, data.get('exact_phrase'))
        self.assertEqual(none_phrase, data.get('none_of_these_words'))
        self.assertEqual(element_status, data.getlist('element_status'))
        self.assertEqual_org(data, q, start_date, end_date, start_amount, end_amount, no_amount, industry, sector, naics_code, 
                    fsc_code, state, county)
        
    def assertEqual_people(self, data, q, start_date, end_date, start_amount, end_amount, no_amount, industry, 
                    sector, naics_code, fsc_code, state, county, first_name, last_name):
        self.assertEqual(first_name, data.get('first_name'))
        self.assertEqual(last_name, data.get('last_name'))
        self.assertEqual_org(data, q, start_date, end_date, start_amount, end_amount, no_amount, industry, sector, naics_code, 
                    fsc_code, state, county)               


    def test_search(self):
        # User Login
        response = self.client.login(username='ted', password='superman')
        print response, '\n\n\n'
        
        # Test 1: Overview Search
        # T 
        response = self.client.get('/search/solicitation/' + '?' + self.url_encode_params({'q':'Water'}), follow=True)
        data = response.context['search_form'].data
        self.assertEqual('Water', data.get('q'))        

        # There is not check currently for this condition because JavaScript blocks it on Overview search
        response = self.client.get('/search/solicitation/' + '?' + self.url_encode_params({'q':''}))
        data = response.context['search_form'].data
        self.assertEqual('', data.get('q'))
        
        # Test 2: Quick Search
        # Multiple NAICS
        response = self.client.get('/search/solicitation/' + '?' + self.url_encode_params({'q':'System NAICS(333412,333415)'}))
        data = response.context['search_form'].data
        self.assertEqual(['333412','333415'],data.getlist('naics_code'))
             
        # State
        response = self.client.get('/search/solicitation/' + '?' + self.url_encode_params({'q':'System STATE(il)'}))
        data = response.context['search_form'].data
        self.assertEqual('IL',data.get('state'))        
        
        # Amount 
        response = self.client.get('/search/solicitation/' + '?' + self.url_encode_params({'q':'System AMT(0,200k)'}))
        data = response.context['search_form'].data
        self.assertEqual(200000, data.get('start_amount'))
        self.assertEqual(True, data.get('no_amount'))
        
        response = self.client.get('/search/solicitation/' + '?' + self.url_encode_params({'q':'System AMT(1,200k)'}))
        data = response.context['search_form'].data
        self.assertEqual('System', data.get('q').strip())
        self.assertEqual(200000, data.get('start_amount'))
        self.assertEqual(False, data.get('no_amount'))
        
        response = self.client.get('/search/solicitation/' + '?' + self.url_encode_params({'q':'System AMT(0,200k-400k)'}))
        data = response.context['search_form'].data
        self.assertEqual('System', data.get('q').strip())
        self.assertEqual(200000, data.get('start_amount'))
        self.assertEqual(400000, data.get('end_amount'))
        self.assertEqual(True, data.get('no_amount'))
        
        #Industry
        #response = self.client.get('/search/solicitation/' + '?' + self.url_encode_params({'q':'System IND()'}))
        #data = response.context['search_form'].data
        #self.assertEqual('System', data.get('q').strip())
        #self.assertEqual(200000, data.get('start_amount'))
        
        # Errors
        # Fake Quick Search Params
        response = self.client.get('/search/solicitation/' + '?' + self.url_encode_params({'q':'System FAKE(Test) boolean(adfs)'}))        
        data = response.context['search_form'].data
        self.assertEqual('System', data.get('q').strip())
        
        
        # Test 3: Advance Search
        self.client.logout()


    def test_adv_search(self):
        #bronze user login
        response = self.client.login(username='john', password='superman')

        response = self.client.post('/search/solicitation/adv/', **{'HTTP_USER_AGENT':'MSIE'})
        self.assertEqual(response['Location'], 'http://testserver/')
        
        self.client.logout()

        # User Login
        response = self.client.login(username='ted', password='superman')
               
        industry = [ind.id for ind in Industry.objects.all()]
        element_status = [t.name for t in Term.objects.solicitation_types()]
        sector = self.get_sector_choices()
        end_date = date.today()
        start_date = date.today() - timedelta(days=90)
        start_amount = '1000'
        end_amount = '3000000'
                
        industry_unicode = self.convert_to_unicode(industry)
        element_status_unicode = self.convert_to_unicode(element_status)
        sector_unicode = self.convert_to_unicode(sector)  
        
        #Elements
        #case 1-Check if it raises an error if Keywords/Exact phrase is missing
        response = self.client.post('/search/solicitation/adv/',{'adv-q':''}, follow=True, **{'HTTP_USER_AGENT':'MSIE'})
        self.assertEqual(response.context['adv_search_form'].errors.values(), [[u'One of the fields are required: Keywords, Exact Phrase']])
        
        #case 2-Check if it raises an error if start date is later than end date
        response = self.client.post('/search/solicitation/adv/',{'adv-q':'system','adv-start_date':end_date + timedelta(days=1),
                                                                 'adv-end_date': end_date}, follow=True, **{'HTTP_USER_AGENT':'MSIE'})
        self.assertEqual(response.context['adv_search_form'].errors.values(), [[u'Start date is later than end date']])
        
        #case 3-Check for keyword
        response = self.client.post('/search/solicitation/adv/',{'adv-q':'system','adv-industry': industry, 
                                                                 'adv-sector':sector, 'adv-start_date':start_date,
                                                                 'adv-element_status':element_status, 'adv-no_amount':True,
                                                                 'adv-end_date': end_date}, follow=True, 
                                                                 **{'HTTP_USER_AGENT':'MSIE'})

        data = QueryDict(response.redirect_chain[0][0].split('?')[1]).copy()
        
        self.assertEqual_element(data, 'system', '', '',start_date.strftime("%m/%d/%y"), end_date.strftime("%m/%d/%y"),
                                 None, None, 'True', industry_unicode, sector_unicode, [], [], [], [], element_status_unicode)
        
        #case 4-Check for exact phrase and custom search date
        response = self.client.post('/search/solicitation/adv/',{'adv-q':'system','adv-industry': industry,
                                                                 'adv-sector':sector, 'adv-element_status':element_status,
                                                                 'adv-start_date':end_date - timedelta(days=575),
                                                                 'adv-end_date': end_date, 'adv-no_amount':True, 
                                                                 'adv-exact_phrase':'hawkeye'}, 
                                                                 follow=True, **{'HTTP_USER_AGENT':'MSIE'})

        data = QueryDict(response.redirect_chain[0][0].split('?')[1]).copy()
        
        self.assertEqual_element(data, 'system', 'hawkeye', '',(end_date - timedelta(days=575)).strftime("%m/%d/%y"), end_date.strftime("%m/%d/%y"),
                                 None, None, 'True', industry_unicode, sector_unicode, [], [], [], [], element_status_unicode)
                
        #case 5-Check for none of these words with a single value
        response = self.client.post('/search/solicitation/adv/',{'adv-q':'system','adv-industry': industry,
                                                                 'adv-sector':sector, 'adv-element_status':element_status,
                                                                 'adv-start_date':start_date,'adv-end_date': end_date,
                                                                 'adv-no_amount':True, 'adv-none_of_these_words':'drainage'},
                                                                 follow=True, **{'HTTP_USER_AGENT':'MSIE'})

        data = QueryDict(response.redirect_chain[0][0].split('?')[1]).copy()
        
        self.assertEqual_element(data, 'system', '', 'drainage',start_date.strftime("%m/%d/%y"), end_date.strftime("%m/%d/%y"),
                                 None, None, 'True', industry_unicode, sector_unicode, [], [], [], [], element_status_unicode)
        
        #case 6-Check for none of these words with multiple values and custom search date
        response = self.client.post('/search/solicitation/adv/',{'adv-q':'system','adv-industry': industry,
                                                                 'adv-sector':sector, 'adv-element_status':element_status,
                                                                 'adv-start_date':end_date - timedelta(days=575),
                                                                 'adv-end_date': end_date,  'adv-no_amount':True,
                                                                 'adv-none_of_these_words':'drainage hawkeye'},
                                                                 follow=True, **{'HTTP_USER_AGENT':'MSIE'})

        data = QueryDict(response.redirect_chain[0][0].split('?')[1]).copy()
        
        self.assertEqual_element(data, 'system', '', 'drainage hawkeye',(end_date-timedelta(days=575)).strftime("%m/%d/%y"), end_date.strftime("%m/%d/%y"),
                                 None, None, 'True', industry_unicode, sector_unicode, [], [], [], [], element_status_unicode)

        #case 7-Check for a single naics code, fsc code, state and 1 year search date
        response = self.client.post('/search/solicitation/adv/',{'adv-q':'system','adv-industry': industry,
                                                                 'adv-sector':sector, 'adv-element_status':element_status,
                                                                 'adv-start_date':end_date - timedelta(days=365), 
                                                                 'adv-end_date': end_date, 'adv-no_amount':True, 
                                                                 'adv-naics_code_autocomplete':'333412',
                                                                 'adv-fsc_code_autocomplete':'41', 
                                                                 'adv-state_autocomplete':'NJ'},
                                                                 follow=True, **{'HTTP_USER_AGENT':'MSIE'})
        
        data = QueryDict(response.redirect_chain[0][0].split('?')[1]).copy()

        self.assertEqual_element(data, 'system', '', '',(end_date-timedelta(days=365)).strftime("%m/%d/%y"), end_date.strftime("%m/%d/%y"),
                                 None, None, 'True', industry_unicode, sector_unicode, ['333412'], ['41'], ['NJ'], [], element_status_unicode)
               
        #case 8-Check for multiple naics code, fsc code, state and custom search date
        response = self.client.post('/search/solicitation/adv/',{'adv-q':'system','adv-industry': industry,
                                                                 'adv-sector':sector, 'adv-element_status':element_status,
                                                                 'adv-start_date':end_date - timedelta(days=575), 
                                                                 'adv-end_date': end_date, 'adv-no_amount':True, 
                                                                 'adv-naics_code_autocomplete':['333412','311812'],
                                                                 'adv-fsc_code_autocomplete':['41','89'], 
                                                                 'adv-state_autocomplete':['NJ','AL']},
                                                                 follow=True, **{'HTTP_USER_AGENT':'MSIE'})
        
        data = QueryDict(response.redirect_chain[0][0].split('?')[1]).copy()

        self.assertEqual_element(data, 'system', '', '',(end_date - timedelta(days=575)).strftime("%m/%d/%y"), end_date.strftime("%m/%d/%y"),
                                 None, None, 'True', industry_unicode, sector_unicode, ['311812', '333412'], 
                                 ['41','89'], ['AL', 'NJ'], [], element_status_unicode)
        
        #case 9-Check for single industry, sector and element types
        response = self.client.post('/search/solicitation/adv/',{'adv-q':'system','adv-industry': '0', 'adv-no_amount':True,
                                                                 'adv-sector':'1', 'adv-start_date':start_date,
                                                                 'adv-element_status':'Awards', 'adv-end_date': end_date},
                                                                  follow=True, **{'HTTP_USER_AGENT':'MSIE'})
        
        data = QueryDict(response.redirect_chain[0][0].split('?')[1]).copy()
        
        self.assertEqual_element(data, 'system', '', '',start_date.strftime("%m/%d/%y"), end_date.strftime("%m/%d/%y"),
                                 None, None, 'True', ['0'], ['1'], [], [], [], [], ['Awards'])
        
        #case 10-Check for start amount, end amount, no amount and multiple industry, sector and element types 
        #which are not default
        response = self.client.post('/search/solicitation/adv/',{'adv-q':'system','adv-industry': ['0','10168296'],
                                                                 'adv-sector':['1','2'], 'adv-no_amount':False, 
                                                                 'adv-element_status':['Amendments', 'Awards'],
                                                                 'adv-start_date':start_date,'adv-end_date': end_date,
                                                                 'adv-start_amount':start_amount, 'adv-end_amount':end_amount},
                                                                 follow=True, **{'HTTP_USER_AGENT':'MSIE'})
        
        data = QueryDict(response.redirect_chain[0][0].split('?')[1]).copy()
        
        self.assertEqual_element(data, 'system', '', '',start_date.strftime("%m/%d/%y"), end_date.strftime("%m/%d/%y"), 
                                 start_amount, end_amount, 'False', ['10168296', '0'], ['1','2'], [], [], [], [], 
                                 ['Amendments', 'Awards'])
        
        #case 11-Check for single state and county
        response = self.client.post('/search/solicitation/adv/',{'adv-q':'system','adv-industry': industry,
                                                                 'adv-sector':sector, 'adv-element_status':element_status,
                                                                 'adv-start_date':end_date - timedelta(days=575), 
                                                                 'adv-end_date': end_date, 'adv-no_amount':True, 
                                                                 'adv-state_autocomplete':'NJ', 
                                                                 'adv-county_autocomplete':'34029'},
                                                                 follow=True, **{'HTTP_USER_AGENT':'MSIE'})
        
        data = QueryDict(response.redirect_chain[0][0].split('?')[1]).copy()

        self.assertEqual_element(data, 'system', '', '',(end_date - timedelta(days=575)).strftime("%m/%d/%y"), end_date.strftime("%m/%d/%y"),
                                 None, None, 'True', industry_unicode, sector_unicode, [], [], ['NJ'], ['34029'], 
                                 element_status_unicode)
        
        #case 12-Check for single state and multiple counties
        response = self.client.post('/search/solicitation/adv/',{'adv-q':'system','adv-industry': industry,
                                                                 'adv-sector':sector, 'adv-element_status':element_status,
                                                                 'adv-start_date':end_date - timedelta(days=575), 
                                                                 'adv-end_date': end_date, 'adv-no_amount':True, 
                                                                 'adv-state_autocomplete':'NJ', 
                                                                 'adv-county_autocomplete':['34029', '34025']},
                                                                 follow=True, **{'HTTP_USER_AGENT':'MSIE'})
        
        data = QueryDict(response.redirect_chain[0][0].split('?')[1]).copy()

        self.assertEqual_element(data, 'system', '', '',(end_date - timedelta(days=575)).strftime("%m/%d/%y"), end_date.strftime("%m/%d/%y"),
                                 None, None, 'True', industry_unicode, sector_unicode, [], [], ['NJ'], 
                                 ['34025', '34029'], element_status_unicode)     

        #Orgs
        #case 1-Check if it raises an error if Keywords is missing
        response = self.client.post('/search/orgs/adv/',{'adv-q':''}, follow=True, **{'HTTP_USER_AGENT':'MSIE'})
        self.assertEqual(response.context['adv_search_form'].errors.values(), [[u'Keywords is required']])
        
        #case 2-Check if it raises an error if start date is later than end date
        response = self.client.post('/search/orgs/adv/',{'adv-q':'system','adv-start_date':end_date + timedelta(days=1),
                                                                 'adv-end_date': end_date}, follow=True, **{'HTTP_USER_AGENT':'MSIE'})
        self.assertEqual(response.context['adv_search_form'].errors.values(), [[u'Start date is later than end date']])
        
        #case 3-Check for keyword
        response = self.client.post('/search/orgs/adv/',{'adv-q':'system','adv-industry': industry,
                                                                 'adv-sector':sector, 
                                                                 'adv-start_date':start_date,'adv-end_date': end_date,
                                                                 'adv-no_amount':True}, follow=True, **{'HTTP_USER_AGENT':'MSIE'})

        data = QueryDict(response.redirect_chain[0][0].split('?')[1]).copy()
        
        self.assertEqual_org(data, 'system', start_date.strftime("%m/%d/%y"), end_date.strftime("%m/%d/%y"),
                                 None, None, 'True', industry_unicode, sector_unicode, [], [], [], [])
        
        #case 4-Check for single industry, sector and 1 year search date
        response = self.client.post('/search/orgs/adv/',{'adv-q':'system','adv-industry': '0',
                                                         'adv-sector':'1', 'adv-start_date':end_date - timedelta(days=365), 
                                                         'adv-end_date': end_date, 'adv-no_amount':True}, 
                                                         follow=True, **{'HTTP_USER_AGENT':'MSIE'})
        
        data = QueryDict(response.redirect_chain[0][0].split('?')[1]).copy()
        
        self.assertEqual_org(data, 'system', (end_date - timedelta(days=365)).strftime("%m/%d/%y"), end_date.strftime("%m/%d/%y"),
                                 None, None, 'True', ['0'], ['1'], [], [], [], [])
        
        #case 5-Check for start amount, end amount, no amount, 1 year for search date and multiple industry, sector which are not default
        response = self.client.post('/search/orgs/adv/',{'adv-q':'system','adv-industry': ['0','10168296'],
                                                         'adv-sector':['1','2'], 'adv-no_amount':False, 
                                                         'adv-start_date':end_date - timedelta(days=365),
                                                         'adv-end_date': end_date, 'adv-start_amount':start_amount, 
                                                         'adv-end_amount':end_amount}, follow=True, **{'HTTP_USER_AGENT':'MSIE'})
        
        data = QueryDict(response.redirect_chain[0][0].split('?')[1]).copy()
        
        self.assertEqual_org(data, 'system', (end_date - timedelta(days=365)).strftime("%m/%d/%y"), 
                                 end_date.strftime("%m/%d/%y"), start_amount, end_amount, 'False', ['10168296', '0'], 
                                 ['1','2'], [], [], [], [])        
        
        #case 6-Check for a single naics code, fsc code, state and 1 year search date
        response = self.client.post('/search/orgs/adv/',{'adv-q':'system','adv-industry': industry,
                                                         'adv-sector':sector, 'adv-no_amount':True,
                                                         'adv-start_date':end_date - timedelta(days=365),
                                                         'adv-end_date': end_date, 'adv-naics_code_autocomplete':'541611', 
                                                         'adv-fsc_code_autocomplete':'70', 'adv-state_autocomplete':'TX'},
                                                         follow=True, **{'HTTP_USER_AGENT':'MSIE'})
        
        data = QueryDict(response.redirect_chain[0][0].split('?')[1]).copy()

        self.assertEqual_org(data, 'system', (end_date - timedelta(days=365)).strftime("%m/%d/%y"), end_date.strftime("%m/%d/%y"),
                                 None, None, 'True', industry_unicode, sector_unicode, ['541611'], ['70'], ['TX'], [])
               
        #case 8-Check for multiple naics code, fsc code, state and custom search date
        response = self.client.post('/search/orgs/adv/',{'adv-q':'system','adv-industry': industry,
                                                         'adv-sector':sector, 'adv-no_amount':True,
                                                         'adv-start_date':end_date - timedelta(days=575),
                                                         'adv-end_date': end_date, 
                                                         'adv-naics_code_autocomplete':['541611','561499'], 
                                                         'adv-fsc_code_autocomplete':['70','A'], 
                                                         'adv-state_autocomplete':['TX', 'CA']},
                                                         follow=True, **{'HTTP_USER_AGENT':'MSIE'})
        
        data = QueryDict(response.redirect_chain[0][0].split('?')[1]).copy()

        self.assertEqual_org(data, 'system', (end_date - timedelta(days=575)).strftime("%m/%d/%y"), end_date.strftime("%m/%d/%y"),
                                 None, None, 'True', industry_unicode, sector_unicode, ['541611','561499'], ['70','A'], 
                                 ['CA', 'TX'], [])

        #case 9-Check for single state and county
        response = self.client.post('/search/orgs/adv/',{'adv-q':'system','adv-industry': industry,
                                                                 'adv-sector':sector, 'adv-start_date':end_date - timedelta(days=575), 
                                                                 'adv-end_date': end_date, 'adv-no_amount':True, 
                                                                 'adv-state_autocomplete':'NJ', 
                                                                 'adv-county_autocomplete':'34029'},
                                                                 follow=True, **{'HTTP_USER_AGENT':'MSIE'})
        
        data = QueryDict(response.redirect_chain[0][0].split('?')[1]).copy()

        self.assertEqual_org(data, 'system', (end_date - timedelta(days=575)).strftime("%m/%d/%y"), end_date.strftime("%m/%d/%y"),
                                 None, None, 'True', industry_unicode, sector_unicode, [], [], ['NJ'], ['34029'])
        
        #case 10-Check for single state and multiple counties
        response = self.client.post('/search/orgs/adv/',{'adv-q':'system','adv-industry': industry,
                                                                 'adv-sector':sector, 'adv-start_date':end_date - timedelta(days=575), 
                                                                 'adv-end_date': end_date, 'adv-no_amount':True, 
                                                                 'adv-state_autocomplete':'NJ', 
                                                                 'adv-county_autocomplete':['34029', '34025']},
                                                                 follow=True, **{'HTTP_USER_AGENT':'MSIE'})
        
        data = QueryDict(response.redirect_chain[0][0].split('?')[1]).copy()

        self.assertEqual_org(data, 'system', (end_date - timedelta(days=575)).strftime("%m/%d/%y"), end_date.strftime("%m/%d/%y"),
                                 None, None, 'True', industry_unicode, sector_unicode, [], [], ['NJ'], 
                                 ['34025', '34029']) 
        
        #People        
        #case 1-Check if it raises an error if Keywords/First name is missing
        response = self.client.post('/search/people/adv/',{'adv-q':''}, follow=True, **{'HTTP_USER_AGENT':'MSIE'})
        self.assertEqual(response.context['adv_search_form'].errors.values(), [[u'One of the fields are required: Keywords, First Name, Last Name']])
        
        #case 2-Check if it raises an error if start date is later than end date
        response = self.client.post('/search/people/adv/',{'adv-q':'system','adv-start_date':end_date + timedelta(days=1),
                                                                 'adv-end_date': end_date}, follow=True, **{'HTTP_USER_AGENT':'MSIE'})
        self.assertEqual(response.context['adv_search_form'].errors.values(), [[u'Start date is later than end date']])
        
        #case 3-Check for keyword
        response = self.client.post('/search/people/adv/',{'adv-q':'system','adv-industry': industry, 'adv-sector':sector, 
                                                                 'adv-start_date':start_date,'adv-end_date': end_date,
                                                                 'adv-no_amount':True}, follow=True, **{'HTTP_USER_AGENT':'MSIE'})

        data = QueryDict(response.redirect_chain[0][0].split('?')[1]).copy()
        
        self.assertEqual_people(data, 'system', start_date.strftime("%m/%d/%y"), end_date.strftime("%m/%d/%y"),
                                 None, None, 'True', industry_unicode, sector_unicode, [], [], [], [], '', '')

        #case 4-Check for first name, single state and custom search date
        response = self.client.post('/search/people/adv/',{'adv-q':'system','adv-industry': industry, 'adv-sector':sector, 
                                                           'adv-start_date':end_date - timedelta(days=575),
                                                           'adv-end_date': end_date, 'adv-no_amount':True, 
                                                           'adv-first_name':'John', 'adv-state_autocomplete':'VA'}, 
                                                           follow=True, **{'HTTP_USER_AGENT':'MSIE'})

        data = QueryDict(response.redirect_chain[0][0].split('?')[1]).copy()
        
        self.assertEqual_people(data, 'system', (end_date - timedelta(days=575)).strftime("%m/%d/%y"), end_date.strftime("%m/%d/%y"),
                                 None, None, 'True', industry_unicode, sector_unicode, [], [], ['VA'], [], 'John', '')
               
        #case 5-Check for multiple state, no amount and custom search date
        response = self.client.post('/search/people/adv/',{'adv-q':'system','adv-industry': industry, 'adv-sector':sector, 
                                                           'adv-start_date':end_date - timedelta(days=575),
                                                           'adv-end_date': end_date, 'adv-no_amount':False, 
                                                           'adv-state_autocomplete':['VA','CA']}, 
                                                           follow=True, **{'HTTP_USER_AGENT':'MSIE'})

        data = QueryDict(response.redirect_chain[0][0].split('?')[1]).copy()
        
        self.assertEqual_people(data, 'system', (end_date - timedelta(days=575)).strftime("%m/%d/%y"), end_date.strftime("%m/%d/%y"),
                                 None, None, 'False', industry_unicode, sector_unicode, [], [], ['CA', 'VA'], [], '', '')
        
        #case 6-Check for last name and single industry and sector and custom search date
        response = self.client.post('/search/people/adv/',{'adv-q':'system','adv-industry': '0', 'adv-sector':'1',
                                                           'adv-start_date':end_date - timedelta(days=575),
                                                           'adv-end_date': end_date, 'adv-no_amount':True,
                                                           'adv-last_name':'Brown'}, follow=True, **{'HTTP_USER_AGENT':'MSIE'})

        data = QueryDict(response.redirect_chain[0][0].split('?')[1]).copy()
        
        self.assertEqual_people(data, 'system', (end_date - timedelta(days=575)).strftime("%m/%d/%y"), end_date.strftime("%m/%d/%y"),
                                 None, None, 'True', ['0'], ['1'], [], [], [], [], '', 'Brown')
        
        #case 7-Check for start amount, end amount and multiple industry, sector which are not default and 1 year search date        
        response = self.client.post('/search/people/adv/',{'adv-q':'system','adv-industry': ['0','10168296'], 
                                                           'adv-sector':['1','2'], 'adv-no_amount':True,
                                                           'adv-start_date':end_date - timedelta(days=365),
                                                           'adv-end_date': end_date, 'adv-start_amount':start_amount, 
                                                           'adv-end_amount':end_amount},
                                                           follow=True, **{'HTTP_USER_AGENT':'MSIE'})
        
        data = QueryDict(response.redirect_chain[0][0].split('?')[1]).copy()
        
        self.assertEqual_people(data, 'system', (end_date - timedelta(days=365)).strftime("%m/%d/%y"), end_date.strftime("%m/%d/%y"),
                                 start_amount, end_amount, 'True', ['10168296','0'], ['1','2'], [], [], [], [], '', '')

        #case 8-Check for single state and county
        response = self.client.post('/search/people/adv/',{'adv-q':'system','adv-industry': industry,
                                                           'adv-sector':sector, 'adv-start_date':end_date - timedelta(days=575), 
                                                           'adv-end_date': end_date, 'adv-no_amount':True, 
                                                           'adv-state_autocomplete':'NJ', 'adv-county_autocomplete':'34029'},
                                                           follow=True, **{'HTTP_USER_AGENT':'MSIE'})
        
        data = QueryDict(response.redirect_chain[0][0].split('?')[1]).copy()

        self.assertEqual_people(data, 'system', (end_date - timedelta(days=575)).strftime("%m/%d/%y"), end_date.strftime("%m/%d/%y"),
                                 None, None, 'True', industry_unicode, sector_unicode, [], [], ['NJ'], ['34029'], '', '')
        
        #case 9-Check for single state and multiple counties
        response = self.client.post('/search/people/adv/',{'adv-q':'system','adv-industry': industry,
                                                           'adv-sector':sector, 'adv-start_date':end_date - timedelta(days=575), 
                                                           'adv-end_date': end_date, 'adv-no_amount':True, 
                                                           'adv-state_autocomplete':'NJ', 'adv-county_autocomplete':['34029', '34025']},
                                                           follow=True, **{'HTTP_USER_AGENT':'MSIE'})
        
        data = QueryDict(response.redirect_chain[0][0].split('?')[1]).copy()

        self.assertEqual_people(data, 'system', (end_date - timedelta(days=575)).strftime("%m/%d/%y"), end_date.strftime("%m/%d/%y"),
                                 None, None, 'True', industry_unicode, sector_unicode, [], [], ['NJ'], 
                                 ['34025', '34029'], '', '')        
    
        self.client.logout()


    def test_search_ajax(self):
        # User Login
        response = self.client.login(username='ted', password='superman')
        print response, '\n\n\n'
        
        end_date =  date(2012, 05, 01)
        start_date = date.today() - timedelta(days=90)
        
        # Test 1: Update Search
        # Elements
        response = self.client.get('/search/solicitation/results/' + '?' + self.url_encode_params({'q':'System',
                                                                                                   'start_date': start_date,
                                                                                                   'end_date': end_date,
                                                                                                   'naics_code': '333412',
                                                                                                   'no_amount': 'True',
                                                                                                   'industries': '10168299,10168295,10168301,10168294,10168296,10168298,10168297,0'}),  
                                                                                                    follow=True)
        results = response.context['results_paginator'].object_list[0]
        self.assertEqual(u'Department of the Army, Army Contracting Command, MICC, MICC - Fort Dix (RC - East)', results.agency_name)

        # Orgs
        response = self.client.get('/search/orgs/results/' + '?' + self.url_encode_params({'q':'System',
                                                                                                   'start_date': date(2011, 10, 13),
                                                                                                   'end_date': end_date,
                                                                                                   'fsc_code': '41',
                                                                                                   'no_amount': 'False',
                                                                                                   'start_amount':'999999990',
                                                                                                   'end_amount': '1999999980'}))
        
        results = response.context['results_paginator'].object_list[0]
        
        self.assertEqual(u'Defense Logistics Agency, DLA Acquisition Locations, DLA Land and Maritime - BSM', results.title)

        # There is not check currently for this condition because JavaScript blocks it on Overview search
        #response = self.client.get('/search/solicitation/results/' + '?' + self.url_encode_params({'q':''}))
        
        
        # Test 2: Quick Search
        # Multiple NAI
        
        
        # User Logout
        self.client.logout()        

    
    def test_save_search(self):
        # User Login
        response = self.client.login(username='ted', password='superman')
        
        # Test 1: Overview Search
        response = self.client.get('/search/save/' + '?' + self.url_encode_params({'q':'Water', 'domain':'2', 'save_search_name':'T1'}))
        self.assertEqual(1, response.context['save_search_id'])
        self.assertEqual('T1', response.context['save_search_name'])
        self.assertTrue('/search/solicitation/adv/' in response.context['url'])
        
        # Test 2: Advance Search
        req = self.init_adv_search_params()
        req.update({'save_search_id':'1', 'save_search_name':'T2'})
        response = self.client.get('/search/save/' + '?' + self.url_encode_params(req))
        self.assertEqual('T2', response.context['save_search_name'])
        
        # Test 3: Edit Save Search
        
        
        # Test 4: Errors
        # TODO: Need to implement Error Handling

        # Logout
        self.client.logout()

    def test_term_autocomplete(self):
        # User Login
        response = self.client.login(username='ted', password='superman')

        type = ['naics_code', 'fsc_code', 'state', 'county']
        for t in type:
            if t != 'county':
                response = self.client.get('/search/terms/auto/' + '?' + self.url_encode_params({'type': t,'term':'asd'}))
            else:
                response = self.client.get('/search/terms/auto/' + '?' + self.url_encode_params({'type': t, 'state': 'NJ', 'term':'asd'}))
            self.assertTrue(response.content.count('id') == 0)
        
            if t != 'state' and t != 'county':
                response = self.client.get('/search/terms/auto/' + '?' + self.url_encode_params({'type': t,'term':'33'}))
            elif t != 'state' and t == 'county' :
                response = self.client.get('/search/terms/auto/' + '?' + self.url_encode_params({'type': t, 'state': 'NJ', 'term':'mo'}))
            else:
                response = self.client.get('/search/terms/auto/' + '?' + self.url_encode_params({'type': t,'term':'re'}))
            
            self.assertTrue(response.content.count('id') > 0)               

            if t =='naics_code':
                term = '333412'
            elif t == 'fsc_code':
                term = '1337'
            elif t == 'state':
                term = 'DC'
            elif t == 'county':
                term = 'ocean'
            
            if t != 'county':
                response = self.client.get('/search/terms/auto/' + '?' + self.url_encode_params({'type': t,'term':term}))
            else:
                response = self.client.get('/search/terms/auto/' + '?' + self.url_encode_params({'type': t, 'state': 'NJ', 'term':term}))
            self.assertTrue(response.content.count('id') == 1)                    
            
        self.client.logout()
