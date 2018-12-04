# home-assistant
My Home Assistant projects

Just been trying to figure out how to make new cards and get to know the frameworks


## Clock Card
![](https://i.imgur.com/L8CFpm6.gif "1")

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


So far mostly a copy/paste/edit of stuff from 
https://github.com/home-assistant/home-assistant-polymer/blob/dev/src/cards/ha-weather-card.js
and
https://github.com/rdehuyss/homeassistant-lovelace-alarm-clock-card/blob/master/alarm-clock-card.js
