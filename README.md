webrender-phantomjs
===================

A standalone web-rendering service that extracts links for crawlers. It also expects to be deployed behind warcprox
and uses that to store the rendered results as WARC records.


API
---

### /render?url={URL}

Renders the given URL in the browser, extracts the relevant links, and passes a summary back to the caller as a JSON object.

This is done using a PhantomJS script based on one provided with PhantomJS.

Running the application
-----------------------

The application runs out of the webrender folder:

    $ cd webrender

For development purposes, run

    $ python manage.py runserver

and go to http://127.0.0.1:8000/webtools

For [production deployment](https://docs.djangoproject.com/en/1.8/howto/deployment/), an example [gunicorn](http://docs.gunicorn.org/en/latest/install.html) configuration is included:

    $ gunicorn -c gunicorn.ini wsgi:application


