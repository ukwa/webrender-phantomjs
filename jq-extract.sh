jq -r ".log.pages[0].renderedContent.text" $1 | base64 -D > extracted-dom.html
jq -r ".log.pages[0].renderedElements[0].content" $1 | base64 -D > extracted-image.png
