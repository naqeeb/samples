from django.conf.urls.defaults import *
from govini.search import SEARCH_DATA_DOMAIN_RECORD, SEARCH_DATA_DOMAIN_ORG, SEARCH_DATA_DOMAIN_PEOPLE, SEARCH_DATA_DOMAIN_DOCUMENT

urlpatterns = patterns('govini.search.views',
                       (r'^terms/$', 'get_term_children'),
                       (r'^terms/auto/$', 'term_autocomplete'),
                       (r'^save/$', 'save_search_query'),

                       (r'^save/feed/$', 'saved_search_feed'),
                       (r'^save/feed/viewall/$', 'view_all'),
                       (r'^save/notify/(?P<save_search_id>\d+)/$', 'notify_saved_search'),

                       (r'^orgs/$', 'search', {'search_data_domain':SEARCH_DATA_DOMAIN_ORG, 'data_url':'search/overview/results.html', 'ajax_url':'/search/orgs/results/'}, 'search_orgs'),
                       (r'^orgs/adv/$', 'adv_search', {'search_data_domain':SEARCH_DATA_DOMAIN_ORG, 'data_url':'search/adv/orgs.html', 'redirect_url':'/search/orgs/', 'popup_url':'search/snippets/adv_solicitation.html'}, 'adv_search_orgs'),
                       (r'^orgs/results/$', 'search_ajax', {'search_data_domain':SEARCH_DATA_DOMAIN_ORG, 'data_url':'search/results/orgs.html'}, 'search_orgs_ajax'),

                       (r'^people/$', 'search',  {'search_data_domain':SEARCH_DATA_DOMAIN_PEOPLE, 'data_url':'search/overview/results.html', 'ajax_url':'/search/people/results/'}, 'search_people'),
                       (r'^people/adv/$', 'adv_search', {'search_data_domain':SEARCH_DATA_DOMAIN_PEOPLE, 'data_url':'search/adv/people.html', 'redirect_url':'/search/people/', 'popup_url':'search/snippets/adv_solicitation.html'}, 'adv_search_people'),
                       (r'^people/results/$', 'search_ajax', {'search_data_domain':SEARCH_DATA_DOMAIN_PEOPLE, 'data_url':'search/results/people.html'}, 'search_people_ajax'),

                       (r'^solicitation/$', 'search',  {'search_data_domain':SEARCH_DATA_DOMAIN_RECORD, 'data_url':'search/overview/results.html', 'ajax_url':'/search/solicitation/results/'}, 'search_solicitation'),
                       (r'^solicitation/adv/$', 'adv_search', {'search_data_domain':SEARCH_DATA_DOMAIN_RECORD, 'data_url':'search/adv/solicitation.html', 'redirect_url':'/search/solicitation/', 'popup_url':'search/snippets/adv_solicitation.html'}, 'adv_search_solicitation'),
                       (r'^solicitation/results/$', 'search_ajax', {'search_data_domain':SEARCH_DATA_DOMAIN_RECORD, 'data_url':'search/results/solicitation.html'}, 'search_solicitation_ajax'),

                       (r'^facets/domain/$', 'domain_facet'),

                       (r'^analytics/ajax/(?P<search_data_domain>\d+)/$', 'search_details_analytics'),
                       (r'^analytics/elements/$', 'search_element_analytics'),
                       (r'^analytics/elements_candle/$', 'search_element_analytics_candle'),



                       # New UI urls
                       (r'^overview/$', 'search'),
                       (r'^overview/analytics/(?P<type>\d+)/$', 'search'),

                       (r'^saved_search/rename/(?P<search_id>\d+)/$', 'rename_saved_search'),
                       (r'^saved_search/$', 'saved_searches'),

                       (r'^save_search_check_exists/(?P<name>[\w.@+-]+)/$', 'save_search_check_exists'),
                       (r'^save_search_popup_reset/(?P<_id>\d+)/$', 'save_search_popup_reset'),

                       )
