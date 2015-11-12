django-phantomjs
================

A Django app. which wraps PhantomJs.

    image/<URL>     Render an PNG image of the URL in question (rasterize.js)
    traffic/<URL>   Return JSON-formatted details of network traffic (netsniff.js)
    urls/<URL>      As with 'traffic' but return a simple list of URLs (netsniff.js)
    imageurls/<URL> Returns a JSON structure containing the same output as "/urls/" and a Base64-encoded 
                    version of the output of "/image/".
    domimage/<URL>  Returns a JSON structure based on the HAR format, containing the rendered URL both as an 
                    image and as the onReady DOM. Any fields POSTed to this endpoint are interpreted as DOM 
                    selectors, which can be used to generated rendered forms of particular sections 
                    of the final page.

The examples directory contains the actual PhantomJS scripts. The scripts directory contains various Python scripts for sending/receiving data.

This application largely depends on the PhantomJS scripts that are supplied with PhantomJS itself.

Running the application
-----------------------

For development purposes, run

    $ python manage.py runserver

and go to http://127.0.0.1:8000/webtools

For [production deployment](https://docs.djangoproject.com/en/1.8/howto/deployment/), an example [gunicorn](http://docs.gunicorn.org/en/latest/install.html) configuration is included:

    $ gunicorn -c gunicorn.ini wsgi:application


