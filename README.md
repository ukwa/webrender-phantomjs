webrender-phantomjs
===================

A standalone web-rendering service that extracts links for crawlers. It also expects to be deployed behind warcprox
and uses that to store the rendered results as WARC records.


API
---

### /render?url={URL}

Renders the given URL in the browser, extracts the relevant links, and passes a summary back to the caller as a JSON object.

This is done using a PhantomJS script based on one provided with PhantomJS.

e.g. an `&` needs to be encoded as %26
 
Additional query parameters: `warc-prefix`, `selectors` and `include-rendered`

Running the application
-----------------------

For development purposes, install [Flask](http://flask.pocoo.org/) and run

    $ FLASK_APP=wrengine.py flask run

and go to http://127.0.0.1:5000/

For production deployment, an example [gunicorn](http://docs.gunicorn.org/en/latest/install.html) configuration is included:

    $ gunicorn -c gunicorn.ini wrengine:app


