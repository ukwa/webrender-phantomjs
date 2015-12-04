from django.conf.urls import patterns, include, url

urlpatterns = patterns( 'phantomjs.views',
	( r'^image/(?P<url>.*)$', 'get_image' ),
	( r'^imageproxy/(?P<url>.*)$', 'get_image_proxy' ),
	( r'^urls/(?P<url>.*)$', 'get_urls' ),
	( r'^traffic/(?P<url>.*)$', 'get_raw' ),
	( r'^imageurls/(?P<url>.*)$', 'get_image_and_urls' ),
	( r'^domimage/(?P<url>.*)$', 'get_dom_image' ),
)
