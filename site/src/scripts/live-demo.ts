/**
 * Live demo client.
 * Posts a transaction payload to the deployed API Gateway endpoint and
 * renders the routing decision. Supports two LLM providers (Bedrock /
 * Anthropic) via the `llm_provider` request-body field, three scenario
 * presets that auto-fill the form, and graceful error handling for the
 * 29s API Gateway timeout that can fire during cold-start invocations.
 */

const API_URL =
  "https://arza8e31vj.execute-api.us-east-1.amazonaws.com/prod/route";

const FETCH_TIMEOUT_MS = 60_000; // generous; API Gateway itself caps at 29s

type Tx = {
  transaction_id:    string;
  bin:               string;
  last4:             string;
  card_type:         string;
  amount:            number;
  currency:          string;
  mcc:               string;
  merchant_country:  string;
  card_country:      string;
};

interface ScoreEntry {
  auth_rate: number;
  estimated_interchange_pct: number;
  score: number;
  weight_auth: number;
  weight_ic: number;
}

interface RouteResponse {
  transaction_id:    string;
  selected_scheme:   string;
  confidence:        number;
  rationale:         string;
  fallback_chain:    { scheme: string; reason: string }[];
  score_breakdown:   Record<string, ScoreEntry>;
  mock_auth_result:  string;
  llm_provider:      string;
}

const SCENARIOS: Record<string, { label: string; tx: Tx }> = {
  fr_grocery: {
    label: "Scenario 1 — FR dual-brand grocery (€150)",
    tx: {
      transaction_id:   "txn-fr-001",
      bin:              "476173",
      last4:            "9999",
      card_type:        "CREDIT",
      amount:           150.0,
      currency:         "EUR",
      mcc:              "5411",
      merchant_country: "FR",
      card_country:     "FR",
    },
  },
  xb_travel: {
    label: "Scenario 2 — Cross-border travel ($2,500)",
    tx: {
      transaction_id:   "txn-xb-001",
      bin:              "476173",
      last4:            "9999",
      card_type:        "CREDIT",
      amount:           2500.0,
      currency:         "USD",
      mcc:              "4722",
      merchant_country: "US",
      card_country:     "FR",
    },
  },
  cb_off: {
    label: "Scenario 3 — Same as #1 (toggle CB off in DynamoDB first)",
    tx: {
      transaction_id:   "txn-fr-cb-off-001",
      bin:              "476173",
      last4:            "9999",
      card_type:        "CREDIT",
      amount:           150.0,
      currency:         "EUR",
      mcc:              "5411",
      merchant_country: "FR",
      card_country:     "FR",
    },
  },
};

function $<T extends HTMLElement = HTMLElement>(sel: string): T {
  const e = document.querySelector<T>(sel);
  if (!e) throw new Error(`missing element: ${sel}`);
  return e;
}

function setForm(tx: Tx) {
  ($("#bin")              as HTMLInputElement).value = tx.bin;
  ($("#last4")            as HTMLInputElement).value = tx.last4;
  ($("#card_type")        as HTMLSelectElement).value = tx.card_type;
  ($("#amount")           as HTMLInputElement).value = String(tx.amount);
  ($("#currency")         as HTMLInputElement).value = tx.currency;
  ($("#mcc")              as HTMLInputElement).value = tx.mcc;
  ($("#merchant_country") as HTMLInputElement).value = tx.merchant_country;
  ($("#card_country")     as HTMLInputElement).value = tx.card_country;
  ($("#transaction_id")   as HTMLInputElement).value = tx.transaction_id;
}

function readForm(): Tx {
  return {
    transaction_id:   ($("#transaction_id")   as HTMLInputElement).value || `txn-${Date.now()}`,
    bin:              ($("#bin")              as HTMLInputElement).value,
    last4:            ($("#last4")            as HTMLInputElement).value,
    card_type:        ($("#card_type")        as HTMLSelectElement).value,
    amount:           parseFloat(($("#amount") as HTMLInputElement).value),
    currency:         ($("#currency")         as HTMLInputElement).value,
    mcc:              ($("#mcc")              as HTMLInputElement).value,
    merchant_country: ($("#merchant_country") as HTMLInputElement).value,
    card_country:     ($("#card_country")     as HTMLInputElement).value,
  };
}

function getProvider(): "bedrock" | "anthropic" {
  const v = (document.querySelector('input[name="provider"]:checked') as HTMLInputElement)?.value;
  return v === "bedrock" ? "bedrock" : "anthropic";
}

function setStatus(state: "idle" | "loading" | "success" | "error" | "timeout", text: string) {
  const el = $("#status-badge");
  const map: Record<string, string> = {
    idle:    "pill pill-muted",
    loading: "pill pill-accent",
    success: "pill pill-good",
    error:   "pill pill-warn",
    timeout: "pill pill-warn",
  };
  el.className = map[state];
  el.textContent = text;
}

function renderDecision(data: RouteResponse, latencyMs: number) {
  const card = $("#decision-card");
  const winner = data.selected_scheme;
  const conf = (data.confidence * 100).toFixed(0);

  const rows = Object.entries(data.score_breakdown)
    .sort((a, b) => b[1].score - a[1].score)
    .map(([scheme, s]) => `
      <tr class="${scheme === winner ? "bg-emerald-50" : ""}">
        <td class="py-2 px-3 font-mono text-sm font-semibold">${scheme}</td>
        <td class="py-2 px-3 font-mono text-sm">${(s.auth_rate * 100).toFixed(1)}%</td>
        <td class="py-2 px-3 font-mono text-sm">${s.estimated_interchange_pct.toFixed(4)}%</td>
        <td class="py-2 px-3 font-mono text-sm font-semibold">${s.score.toFixed(4)}</td>
        <td class="py-2 px-3 font-mono text-xs text-muted">${s.weight_auth}/${s.weight_ic}</td>
      </tr>`).join("");

  const fb = data.fallback_chain.length === 0
    ? `<p class="text-sm text-muted italic">No fallback available.</p>`
    : data.fallback_chain.map(f =>
        `<p class="text-sm"><span class="font-mono font-semibold text-accent">${f.scheme}</span> &middot; <span class="text-muted">${f.reason}</span></p>`).join("");

  card.innerHTML = `
    <div class="bg-paper border-2 border-accent rounded-lg p-5 md:p-6 font-serif text-ink mb-6">
      <div class="flex items-baseline justify-between mb-4 flex-wrap gap-2">
        <div>
          <div class="text-xs font-sans uppercase tracking-widest text-muted">Routing decision</div>
          <div class="text-2xl md:text-3xl font-semibold text-accent mt-1">${winner}</div>
        </div>
        <div class="text-right">
          <div class="text-xs font-sans uppercase tracking-widest text-muted">Confidence</div>
          <div class="text-2xl font-semibold text-accent2 font-mono">${conf}%</div>
        </div>
      </div>
      <p class="mb-5">${data.rationale}</p>
      <div class="mb-5 overflow-x-auto">
        <table class="w-full text-left border border-rule rounded">
          <thead class="bg-rule/40">
            <tr>
              <th class="py-2 px-3 font-sans text-sm font-semibold text-accent">Scheme</th>
              <th class="py-2 px-3 font-sans text-sm font-semibold text-accent">Auth rate</th>
              <th class="py-2 px-3 font-sans text-sm font-semibold text-accent">Interchange</th>
              <th class="py-2 px-3 font-sans text-sm font-semibold text-accent">Score</th>
              <th class="py-2 px-3 font-sans text-sm font-semibold text-accent">Weights</th>
            </tr>
          </thead>
          <tbody>${rows}</tbody>
        </table>
      </div>
      <div class="mb-4">
        <div class="text-xs font-sans uppercase tracking-widest text-muted mb-1">Fallback chain</div>
        ${fb}
      </div>
      <div class="pt-3 border-t border-rule flex items-center gap-3 flex-wrap">
        <span class="pill ${data.mock_auth_result === "APPROVED" ? "pill-good" : "pill-warn"}">MockSchemeGateway &middot; ${data.mock_auth_result}</span>
        <span class="pill pill-accent">Provider &middot; ${data.llm_provider}</span>
        <span class="pill pill-muted">Latency &middot; ${(latencyMs / 1000).toFixed(1)}s</span>
      </div>
    </div>
  `;

  ($("#raw-json") as HTMLElement).textContent = JSON.stringify(data, null, 2);
  ($("#raw-section") as HTMLElement).classList.remove("hidden");
}

function renderError(title: string, detail: string, raw?: string) {
  const card = $("#decision-card");
  card.innerHTML = `
    <div class="bg-amber-50 border-2 border-amber-300 rounded-lg p-5 md:p-6 font-serif text-ink mb-6">
      <div class="text-amber-900 font-semibold mb-2">${title}</div>
      <p class="text-amber-900/80">${detail}</p>
      ${raw ? `<pre class="mt-4 text-xs font-mono whitespace-pre-wrap text-amber-900/70">${raw}</pre>` : ""}
    </div>
  `;
}

async function submit() {
  const tx = readForm();
  const provider = getProvider();
  const payload = { ...tx, llm_provider: provider };

  setStatus("loading", `Calling Lambda via ${provider}…`);
  $("#decision-card").innerHTML = `
    <div class="text-muted italic flex items-center gap-3">
      <span class="inline-block w-3 h-3 rounded-full bg-accent animate-pulse"></span>
      Waiting for response. Cold starts can take up to 40 seconds &mdash; API Gateway will time out at 29s.
    </div>`;
  ($("#raw-section") as HTMLElement).classList.add("hidden");

  const start = performance.now();
  const ac = new AbortController();
  const timer = setTimeout(() => ac.abort(), FETCH_TIMEOUT_MS);

  try {
    const resp = await fetch(API_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      signal: ac.signal,
    });
    clearTimeout(timer);
    const latency = performance.now() - start;
    const text = await resp.text();
    let json: any;
    try { json = JSON.parse(text); } catch { json = { raw: text }; }

    if (resp.status === 200 && json && json.selected_scheme) {
      setStatus("success", `200 OK · ${(latency / 1000).toFixed(1)}s`);
      renderDecision(json as RouteResponse, latency);
      return;
    }

    if (resp.status === 504 || (json && json.message === "Endpoint request timed out")) {
      setStatus("timeout", `Gateway timeout · ${(latency / 1000).toFixed(1)}s`);
      renderError(
        "API Gateway timed out (29s cap)",
        "The Lambda is still running and will finish in another ~10 seconds, but API Gateway already returned. " +
        "Try Scenario 3 (CB disabled) which finishes faster (~26s warm), or use the pre-recorded version.",
        JSON.stringify(json, null, 2),
      );
      return;
    }

    if (resp.status === 500 && json && /Throttling/i.test(json.detail ?? "")) {
      setStatus("error", `500 · Bedrock throttled`);
      renderError(
        "Bedrock model access not granted",
        "Switch the provider toggle to Anthropic above. Bedrock access on this account is still being resolved with AWS Support.",
        JSON.stringify(json, null, 2),
      );
      return;
    }

    setStatus("error", `HTTP ${resp.status}`);
    renderError(`HTTP ${resp.status}`, "Unexpected response from the API.", JSON.stringify(json, null, 2));
  } catch (err: any) {
    clearTimeout(timer);
    const latency = performance.now() - start;
    if (err?.name === "AbortError") {
      setStatus("timeout", `Client timeout · ${(latency / 1000).toFixed(1)}s`);
      renderError("Client-side timeout", "The browser gave up waiting (60s). The Lambda may have completed in the background.");
    } else {
      setStatus("error", "Network error");
      renderError("Network error", String(err?.message ?? err));
    }
  }
}

function init() {
  setForm(SCENARIOS.fr_grocery.tx);

  const sel = $("#scenario-select") as HTMLSelectElement;
  Object.entries(SCENARIOS).forEach(([key, s]) => {
    const opt = document.createElement("option");
    opt.value = key;
    opt.textContent = s.label;
    sel.appendChild(opt);
  });
  sel.addEventListener("change", () => {
    const s = SCENARIOS[sel.value];
    if (s) setForm(s.tx);
  });

  $("#submit-btn").addEventListener("click", submit);
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", init);
} else {
  init();
}
