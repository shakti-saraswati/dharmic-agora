async function loadSeedClaims() {
  const container = document.getElementById("seed-claims");
  if (!container) return;

  try {
    const response = await fetch("./data/seed_claims.json");
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    const payload = await response.json();
    const claims = Array.isArray(payload.claims) ? payload.claims : [];
    if (!claims.length) {
      container.innerHTML = "<p>No seed claims available yet.</p>";
      return;
    }
    container.innerHTML = claims
      .map(
        (claim) => `
          <article class="claim-card">
            <h3>${escapeHtml(claim.title || "")}</h3>
            <div class="claim-meta">
              <span class="pill">${escapeHtml(claim.node || "unknown-node")}</span>
              <span class="pill">${escapeHtml(claim.requested_stage || "unscoped")}</span>
              <span class="pill">${escapeHtml(claim.status || "unknown")}</span>
            </div>
            <p>${escapeHtml(claim.summary || "")}</p>
            <p><a href="../${escapeAttr(claim.claim_path || "")}">Claim packet</a></p>
          </article>
        `
      )
      .join("");
  } catch (error) {
    container.innerHTML = `<p>Unable to load seed claims: ${escapeHtml(String(error))}</p>`;
  }
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function escapeAttr(value) {
  return escapeHtml(value).replaceAll("`", "&#96;");
}

void loadSeedClaims();

