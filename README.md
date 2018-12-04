# home-assistant
My Home Assistant projects

Just been trying to figure out how to make new cards and get to know the frameworks


## Clock Card
My first real try at a custom HA Lovelace card. 
The clock card requires the following to be put into the ui-lovelace.yaml file
```
resources:
  - url: /local/clock-card.js
    type: js
  - url: https://unpkg.com/moment@2.22.2/min/moment.min.js
    type: js
```

It still needs a bit of work with regards to using local formats and so forth.
