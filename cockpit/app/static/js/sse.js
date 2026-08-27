// sse.js — the live SSE event stream (GET /api/events) and its dispatch to
// every other view. Unchanged behaviour from the old app.js.
import { state } from './state.js';
import { toast } from './format.js';
import { updateNodeCardMetrics, loadNodes } from './nodes.js';
import { updateSelectedMetrics, scheduleSelectedRunRefresh } from './selected-panel.js';
import { renderHero } from './hero.js';
import { refreshEventsLogIfActive } from './events.js';
import { scheduleRfEnvironmentRefresh } from './rf.js';

export function initSSE() {
  const dot = document.getElementById('dot-sse');

  function connect() {
    const es = new EventSource('/api/events');

    es.onopen = () => { dot.classList.add('ok'); };

    es.onmessage = (e) => {
      try { handleEvent(JSON.parse(e.data)); } catch (_) {}
    };

    es.onerror = () => {
      dot.classList.remove('ok');
      es.close();
      setTimeout(connect, 4000);
    };
  }

  connect();
}

function handleEvent(ev) {
  switch (ev.type) {
    case 'uplink': {
      const eui  = ev.dev_eui;
      const prev = state.devMetrics[eui] || {};
      state.devMetrics[eui] = {
        rssi:            ev.rssi_dbm,
        snr:             ev.snr_db,
        sf:              ev.sf,
        f_cnt:           ev.f_cnt,
        pdr:             ev.pdr,
        downlinks_sent:  prev.downlinks_sent,
        acked:           prev.acked,
        dl_pdr:          prev.dl_pdr,
        lastUplinkAt:    ev.last_uplink_at,
        intervalSeconds: ev.interval_seconds,
      };
      updateNodeCardMetrics(eui);
      updateSelectedMetrics(eui);
      renderHero(); // a fresh packet can advance a run's live progress fraction
      const selNode = state.nodesById[state.selectedNodeId];
      if (selNode && selNode.kind === 'device' && selNode.eui === eui) {
        scheduleSelectedRunRefresh();
      }
      break;
    }
    case 'ack': {
      const eui = ev.dev_eui;
      if (state.devMetrics[eui]) {
        state.devMetrics[eui].acked  = ev.acked;
        state.devMetrics[eui].dl_pdr = ev.downlink_pdr;
      }
      refreshEventsLogIfActive(); // Stage 1 — a durable downlink_acked/nacked row just landed
      break;
    }
    case 'join':
      toast(`Join: ${ev.dev_eui} → DevAddr ${ev.dev_addr}`);
      refreshEventsLogIfActive(); // Stage 1 — a durable join row just landed
      break;
    case 'coex':
      scheduleRfEnvironmentRefresh();
      break;
    case 'nodes':
      loadNodes();
      refreshEventsLogIfActive(); // Stage 1 — run/placement/gateway events land here too
      break;
  }
}
