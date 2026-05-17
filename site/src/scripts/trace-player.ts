/**
 * Terminal trace player.
 * Drives the animated reveal of a pre-recorded agent trace inside an element
 * marked with [data-trace-root]. Picks scenario from a <select>, plays steps
 * with a small delay, types out thought text character-by-character, and
 * shows final decision card at the end.
 */

type ToolCallStep = { type: "tool_call"; id: string; tool: string; input: unknown };
type ToolResultStep = { type: "tool_result"; id: string; output: unknown };
type ThoughtStep = { type: "thought"; text: string };
type FinalStep = { type: "final"; decision: Decision };
type Step = ToolCallStep | ToolResultStep | ThoughtStep | FinalStep;

interface Decision {
  selected_scheme: string;
  confidence: number;
  rationale: string;
  fallback_chain: Array<{ scheme: string; reason: string }>;
  score_breakdown: Record<string, {
    auth_rate: number;
    estimated_interchange_pct: number;
    score: number;
    weight_auth: number;
    weight_ic: number;
  }>;
}

interface Scenario {
  id: string;
  label: string;
  summary: string;
  transaction: Record<string, unknown>;
  expected_outcome: Record<string, unknown>;
  steps: Step[];
  mock_auth_result: string;
}

const STEP_DELAY_MS = 320;
const TYPE_SPEED_MS = 8;

function el(tag: string, cls?: string, html?: string): HTMLElement {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (html != null) e.innerHTML = html;
  return e;
}

function fmtJson(value: unknown): string {
  return JSON.stringify(value, null, 2);
}

async function typeInto(target: HTMLElement, text: string, speed: number): Promise<void> {
  for (let i = 0; i < text.length; i++) {
    target.textContent = text.slice(0, i + 1);
    await new Promise(r => setTimeout(r, speed));
  }
}

function buildToolCall(step: ToolCallStep): HTMLElement {
  const wrap = el("div", "mb-3");
  const head = el("div", "text-accent");
  head.innerHTML = `<span class="text-termdim">→ tool_call</span>  <span class="font-semibold">${step.tool}</span>  <span class="text-termdim">[${step.id}]</span>`;
  const body = el("pre", "text-termfg/90 ml-4 mt-1");
  body.textContent = fmtJson(step.input);
  wrap.appendChild(head);
  wrap.appendChild(body);
  return wrap;
}

function buildToolResult(step: ToolResultStep): HTMLElement {
  const wrap = el("div", "mb-3");
  const head = el("div", "text-emerald-300");
  head.innerHTML = `<span class="text-termdim">← tool_result</span>  <span class="text-termdim">[${step.id}]</span>`;
  const body = el("pre", "text-emerald-100/90 ml-4 mt-1");
  body.textContent = fmtJson(step.output);
  wrap.appendChild(head);
  wrap.appendChild(body);
  return wrap;
}

function buildThought(): { container: HTMLElement; target: HTMLElement } {
  const wrap = el("div", "mb-3");
  const head = el("div", "text-amber-300");
  head.innerHTML = `<span class="text-termdim">▸ reasoning</span>`;
  const body = el("div", "text-amber-100/90 ml-4 mt-1 whitespace-pre-wrap");
  wrap.appendChild(head);
  wrap.appendChild(body);
  return { container: wrap, target: body };
}

function buildFinalCard(decision: Decision, mockAuth: string): HTMLElement {
  const winner = decision.selected_scheme;
  const conf = (decision.confidence * 100).toFixed(0);
  const schemeRows = Object.entries(decision.score_breakdown)
    .sort((a, b) => b[1].score - a[1].score)
    .map(([scheme, s]) => `
      <tr class="${scheme === winner ? "bg-emerald-50" : ""}">
        <td class="py-2 px-3 font-mono text-sm font-semibold">${scheme}</td>
        <td class="py-2 px-3 font-mono text-sm">${(s.auth_rate * 100).toFixed(1)}%</td>
        <td class="py-2 px-3 font-mono text-sm">${s.estimated_interchange_pct.toFixed(3)}%</td>
        <td class="py-2 px-3 font-mono text-sm font-semibold">${s.score.toFixed(4)}</td>
        <td class="py-2 px-3 font-mono text-xs text-muted">${s.weight_auth}/${s.weight_ic}</td>
      </tr>`).join("");

  const fb = decision.fallback_chain.length === 0
    ? `<p class="text-sm text-muted italic">No fallback available.</p>`
    : decision.fallback_chain.map(f =>
        `<p class="text-sm"><span class="font-mono font-semibold text-accent">${f.scheme}</span> &middot; <span class="text-muted">${f.reason}</span></p>`).join("");

  const wrap = el("div", "mt-6 bg-paper border-2 border-accent rounded-lg p-5 md:p-6 font-serif text-ink");
  wrap.innerHTML = `
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
    <p class="mb-5">${decision.rationale}</p>
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
        <tbody>${schemeRows}</tbody>
      </table>
    </div>
    <div class="mb-4">
      <div class="text-xs font-sans uppercase tracking-widest text-muted mb-1">Fallback chain</div>
      ${fb}
    </div>
    <div class="pt-3 border-t border-rule flex items-center gap-3 flex-wrap">
      <span class="pill ${mockAuth === "APPROVED" ? "pill-good" : "pill-warn"}">MockSchemeGateway &middot; ${mockAuth}</span>
      <span class="pill pill-muted">Total tool calls: ${
        Object.keys(decision.score_breakdown).length === 1 ? "trimmed by adaptive path" : "full"
      }</span>
    </div>
  `;
  return wrap;
}

function buildTxnPanel(s: Scenario): HTMLElement {
  const t = s.transaction;
  const wrap = el("div", "bg-paper border border-rule rounded-md p-4 mb-4 text-sm font-mono");
  wrap.innerHTML = `
    <div class="text-xs font-sans uppercase tracking-widest text-muted mb-2">POST /route payload</div>
    <pre class="whitespace-pre-wrap text-ink/80">${fmtJson(t)}</pre>
  `;
  return wrap;
}

class TracePlayer {
  private scenarios: Scenario[] = [];
  private currentScenario: Scenario | null = null;
  private select: HTMLSelectElement;
  private termBody: HTMLElement;
  private txnPanel: HTMLElement;
  private summary: HTMLElement;
  private decisionPanel: HTMLElement;
  private playBtn: HTMLButtonElement;
  private resetBtn: HTMLButtonElement;
  private liveToggle: HTMLInputElement;
  private liveBanner: HTMLElement;
  private playing = false;
  private cancelToken: { cancelled: boolean } = { cancelled: false };

  constructor(root: HTMLElement, scenarios: Scenario[]) {
    this.scenarios = scenarios;
    this.select = root.querySelector("[data-scenario-select]") as HTMLSelectElement;
    this.termBody = root.querySelector("[data-term-body]") as HTMLElement;
    this.txnPanel = root.querySelector("[data-txn-panel]") as HTMLElement;
    this.summary = root.querySelector("[data-scenario-summary]") as HTMLElement;
    this.decisionPanel = root.querySelector("[data-decision-panel]") as HTMLElement;
    this.playBtn = root.querySelector("[data-play-btn]") as HTMLButtonElement;
    this.resetBtn = root.querySelector("[data-reset-btn]") as HTMLButtonElement;
    this.liveToggle = root.querySelector("[data-live-toggle]") as HTMLInputElement;
    this.liveBanner = root.querySelector("[data-live-banner]") as HTMLElement;

    for (const s of scenarios) {
      const opt = document.createElement("option");
      opt.value = s.id;
      opt.textContent = s.label;
      this.select.appendChild(opt);
    }
    this.select.addEventListener("change", () => this.selectScenario(this.select.value));
    this.playBtn.addEventListener("click", () => this.play());
    this.resetBtn.addEventListener("click", () => this.reset(true));
    this.liveToggle.addEventListener("change", () => {
      this.liveBanner.classList.toggle("hidden", !this.liveToggle.checked);
    });

    this.selectScenario(scenarios[0]!.id);
  }

  private selectScenario(id: string) {
    this.cancelToken.cancelled = true;
    this.currentScenario = this.scenarios.find(s => s.id === id) ?? null;
    if (!this.currentScenario) return;
    this.select.value = id;
    this.summary.textContent = this.currentScenario.summary;
    this.txnPanel.replaceChildren(buildTxnPanel(this.currentScenario));
    this.reset(false);
  }

  private reset(resetSelect: boolean) {
    this.cancelToken.cancelled = true;
    this.cancelToken = { cancelled: false };
    this.playing = false;
    this.termBody.innerHTML = "";
    this.decisionPanel.innerHTML = "";
    this.playBtn.disabled = false;
    this.playBtn.textContent = "▶ Play trace";
    if (resetSelect) {
      // no-op, but reserved
    }
  }

  private async play() {
    if (!this.currentScenario) return;
    if (this.playing) return;
    this.playing = true;
    this.playBtn.disabled = true;
    this.playBtn.textContent = "Running…";
    this.termBody.innerHTML = "";
    this.decisionPanel.innerHTML = "";

    const headerLine = el("div", "text-termdim mb-2");
    headerLine.textContent = `$ bedrock_routing_agent.run(${this.currentScenario.id})`;
    this.termBody.appendChild(headerLine);

    const local = this.cancelToken;
    for (const step of this.currentScenario.steps) {
      if (local.cancelled) return;
      if (step.type === "tool_call") {
        this.termBody.appendChild(buildToolCall(step));
      } else if (step.type === "tool_result") {
        this.termBody.appendChild(buildToolResult(step));
      } else if (step.type === "thought") {
        const t = buildThought();
        this.termBody.appendChild(t.container);
        await typeInto(t.target, step.text, TYPE_SPEED_MS);
      } else if (step.type === "final") {
        const done = el("div", "text-emerald-300 mt-3");
        done.innerHTML = `<span class="text-termdim">✓ end_turn</span>  agent emitted final JSON`;
        this.termBody.appendChild(done);
        this.decisionPanel.appendChild(buildFinalCard(step.decision, this.currentScenario.mock_auth_result));
      }
      this.termBody.scrollTop = this.termBody.scrollHeight;
      await new Promise(r => setTimeout(r, STEP_DELAY_MS));
    }

    this.playing = false;
    this.playBtn.disabled = false;
    this.playBtn.textContent = "▶ Replay";
  }
}

function init() {
  const root = document.querySelector<HTMLElement>("[data-trace-root]");
  if (!root) return;
  const dataEl = document.getElementById("trace-scenarios");
  if (!dataEl) return;
  const scenarios = JSON.parse(dataEl.textContent || "[]") as Scenario[];
  new TracePlayer(root, scenarios);
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", init);
} else {
  init();
}
