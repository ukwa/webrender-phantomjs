django-phantomjs
================

A Django app. which wraps PhantomJs.

    image/<URL>     Render an image of the URL in question (rasterize.js)
    traffic/<URL>   Return JSON-formatted details of network traffic (netsniff.js)
    urls/<URL>      As with 'traffic' but return a simple list of URLs (netsniff.js)
    imageurls/<URL> Returns a JSON structure containing the same output as "/urls/" and a Base64-encoded version of the output of "/image/".

The scripts directory contains various Python scripts for sending/receiving data.

