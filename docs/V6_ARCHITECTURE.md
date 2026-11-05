# Deep Research Engine v6.0 — Frontier Architecture Blueprint

**Date:** 2026-11-05 · **Status:** Implemented in `dr_engine/tools/frontier.py` & Gates E11/R16 · **Scope:** Global

---

## 0. Theoretical Leap & Overview

The Deep Research v6.0 architecture bridges the final gap between deterministic fact compilation and **institutional-grade quantitative epistemology**.

While v5.0 established:
- **Layer L1:** Cryptographic verbatim quotes & immutable snapshots (`evidence.py`).
- **Layer L2:** AST-compiled arithmetic and deterministic scenario bounds (`calc.py` `[C###]`).
- **Layer L3:** Doubt-Driven Development & Kill Hypotheses.
- **Layer L4:** Structural Causal Models (SCM), Pearl's $d$-separation, and counterfactual $do(X=x)$ shocks (`causal.py`).
- **Layer L5:** Epistemic Index v5.0 with shingle Jaccard syndication detection & DerSimonian-Laird meta-analytic heterogeneity (`dialectics.py`, `formula.py`).

**v6.0 operationalizes four fundamental mathematical theorems previously absent from autonomous research systems:**
1. **Bayesian Value of Information (VoI) & Optimal Stopping:** Mathematical criteria for search termination via analytic Expected Value of Sample Information (EVSI) and Expected Value of Perfect Information (EVPI).
2. **Adversarial Game-Theoretic Epistemic Tournaments:** Multi-agent zero-sum belief contests (PROPONENT vs SKEPTIC vs RED_TEAM) converging to an exact Nash Equilibrium verified by unilateral deviation sweeps.
3. **Non-Linear Dynamics & Tipping Points:** Linearization of the causal DAG into a Jacobian matrix, power iteration estimation of dominant eigenvalues for **Critical Slowing Down** ($|\lambda| \ge 0.9$), Gaussian-elimination bifurcation scans, and threshold cascade contagion.
4. **Topological Claim Spaces:** Undirected dual graph of claims and citations, Tarjan's articulation points and bridge discovery, unchallenged-claim structural blind spot detection, and spectral 2D narrative manifold layout without neural embeddings.

---

## 1. Mathematical Foundations & Implementation

### 1.1 Bayesian EVSI & Optimal Stopping (`frontier.py evsi`)

Prior to v6.0, search termination was either arbitrary (human budget) or heuristic (Chapman saturation). v6.0 models search as an optimal stopping problem under uncertainty:

1. **Beta-Bernoulli Posterior:**
   Given evidence records $E = \{e_1, \dots, e_k\}$ with stances $s_i \in \{\text{supports}, \text{contradicts}\}$ and source tier reliabilities $r_i \in [0.40, 0.95]$:
   $$\alpha = \alpha_0 + \sum_{e_i \in \text{supports}} r_i + \sum_{e_i \in \text{contradicts}} (1 - r_i)$$
   $$\beta = \beta_0 + \sum_{e_i \in \text{supports}} (1 - r_i) + \sum_{e_i \in \text{contradicts}} r_i$$
   Posterior mean $\mu = \frac{\alpha}{\alpha + \beta}$, variance $\sigma^2 = \frac{\alpha \beta}{(\alpha + \beta)^2 (\alpha + \beta + 1)}$.

2. **Analytic EVSI:**
   With decision value function $V(m) = \max(m, 1 - m)$ (0/1-loss optimal action):
   $$P(\text{next supports}) = \mu r_{next} + (1 - \mu)(1 - r_{next})$$
   $$\text{EVSI} = P(\text{sup}) V\left(\frac{\alpha + r_{next}}{\alpha + \beta + 1}\right) + P(\text{contra}) V\left(\frac{\alpha + 1 - r_{next}}{\alpha + \beta + 1}\right) - V(\mu)$$
   
   **Stopping Rule:** If $\text{EVSI} \le \text{cost}$, discovery yields `STOP_SATURATED`. Otherwise, `CONTINUE`.
   **Gate E11 Safeguard:** A `STOP_SATURATED` verdict is rejected if total searches $< 12$, preserving the E4 minimum search floor.

---

### 1.2 Adversarial Epistemic Tournaments (`frontier.py tournament`)

Rather than trusting a single LLM's assessment, claims are subjected to a finite game:
- **Agents:** PROPONENT (majority maximizer), SKEPTIC (contrarian challenger), RED_TEAM (adversarial liquidator targeting the strongest claim).
- **Payoff Matrix:** Payoff on claim $c$ is $+1$ if agent's stance matches evidence-weighted ground truth, $-1$ otherwise.
- **Kelly Belief Bets:** Stake sizing proportional to empirical edge over the ledger: $f^* = \max(0, \text{score} / n) / 2$.
- **Nash Equilibrium Verification:** Deterministic exhaustive sweep of all unilateral single-claim stance deviations. If no agent can strictly improve its total score, the epistemic state has converged to a Nash Equilibrium.

---

### 1.3 Non-Linear Dynamics & Tipping Points (`frontier.py dynamics`)

Real-world phenomena exhibit phase transitions and non-linear collapses:
1. **Jacobian Construction:** From the DAG edges $u \xrightarrow{\beta} v$, compute $J_{v, u} = \beta = \frac{\partial v}{\partial u}$.
2. **Critical Slowing Down:** Dominant eigenvalue $\lambda_{\max}$ is calculated via power iteration. If $|\lambda_{\max}| \ge 0.9$, the system exhibits critical slowing down—minor shocks fail to dissipate and trigger regime shifts.
3. **Bifurcation Scanning:** Solve the fixed point $(I - J) x = s$ using Gaussian elimination with partial pivoting across parameter range $[lo, hi]$. The tipping point is the parameter value where the outcome flips sign or crosses stability bounds.
4. **Threshold Cascade Simulation:** Breadth-first deterministic propagation where a node activates when active parent weight fraction exceeds threshold $\theta$.

---

### 1.4 Topological Claim Space (`frontier.py topology`)

1. **Dual Bipartite-Conflict Graph:** Nodes consist of claims and cited evidence. Edges connect claims to citations and conflicting claims to each other.
2. **Tarjan Articulation Points & Bridges:** Identifies single points of epistemic failure—claims whose removal disconnects the evidence graph.
3. **Unchallenged Claim Blind Spots:** Automatically detects claims with zero contradicting evidence and zero conflict edges (`blind_spots_unchallenged_claims`).
4. **Spectral 2D Manifold:** Power iteration on the normalized adjacency matrix followed by deflation yields the first two non-trivial eigenvectors $(v_1, v_2)$, projecting claims onto a 2D narrative manifold without external embedding models.

---

## 2. Gate Integration (E11 & R16)

- **Gate E11 (Evidence Stage):** Verifies all v6.0 JSON artifacts exist with valid SHA-256 hashes when `require_v6_frontier` is enabled in `quotas.json` or artifacts are present. Forbids `STOP_SATURATED` if logged searches $< 12$.
- **Gate R16 (Report Stage):** Enforces that the final report discusses the EVSI verdict, tournament Nash equilibrium, tipping point/eigenvalue, and claim-space blind spots.
