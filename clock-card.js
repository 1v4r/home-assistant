class ClockCard extends Polymer.Element {
  
    static get template() {
      return Polymer.html`
            <style>
          :host {
            cursor: pointer;
          }
          .content {
            padding: 24px 16px 16px;
          }
          .name {
            margin-left: 16px;
            font-size: 16px;
            color: var(--secondary-text-color);
          }
          .now {
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
          }
          .main {
            display: flex;
            align-items: center;
            margin-right: 32px;
          }
          .main .clock {
            font-size: 52px;
            line-height: 1em;
            position: relative;
          }
          .date {
            font-family: var(--paper-font-headline_-_font-family);
            -webkit-font-smoothing: var(--paper-font-headline_-_-webkit-font-smoothing);
            font-size: var(--paper-font-headline_-_font-size);
            font-weight: var(--paper-font-headline_-_font-weight);
            letter-spacing: var(--paper-font-headline_-_letter-spacing);
            line-height: var(--paper-font-headline_-_line-height);
            text-rendering: var(--paper-font-common-expensive-kerning_-_text-rendering);
            opacity: var(--dark-primary-opacity);
          }
        </style>
        <ha-card>
          <div class="content">
            <div class="now">
              <div class="main">
                <div class="clock" id="time"></div>
              </div>
              <div class="date">
                        <div id="date"></div>
              </div>
            </div>
          </div>
        </ha-card>
       `
    }
    
    static get properties() {
      return {
        _hass: Object
      }
    }
    
    ready() {
      super.ready();
      this.time = this.$.time;
      this.date = this.$.date;
      
      this._updateTime();
      setInterval(() => this._updateTime(), 500);
    }
    
    setConfig(config) {
      this.config = config;
    }
    
    set hass(hass) {
      this._hass = hass;
    }

    _updateTime(force = true) { 
      let moment = require('moment');
      require('locale/nl.js');
      moment().locale(this._hass.language);
      this.time.innerHTML = moment().format('LTS');
      this.date.innerHTML = moment().format('ddd DD/MM/YYYY');
    }

    // The height of your card. Home Assistant uses this to automatically
    // distribute all cards over the available columns.
    getCardSize() {
      return 3;
    }
  }
  
  customElements.define('clock-card', ClockCard);
