# home-assistant
My Home Assistant projects

Just been trying to figure out how to make new cards and get to know the frameworks


The clock card requires the following to be put into the ui-lovelace.yaml file
```
resources:
  - url: /local/clock-card.js
    type: js
  - url: https://unpkg.com/moment@2.22.2/min/moment.min.js
    type: js
```
