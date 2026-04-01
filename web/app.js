const form = document.getElementById("converterForm");
const previewBtn = document.getElementById("previewBtn");
const cards = document.getElementById("cards");
const recommendationBox = document.getElementById("recommendationBox");
const sourceCount = document.getElementById("sourceCount");
const templateName = document.getElementById("templateName");
const statusText = document.getElementById("statusText");
const sourcesInput = document.getElementById("sources");
const templateInput = document.getElementById("template");

function updateHeader() {
  sourceCount.textContent = `${sourcesInput.files.length} arquivo(s)`;
  templateName.textContent = templateInput.files[0]?.name || "Nenhum";
}

function buildFormData() {
  const data = new FormData();
  data.set("geometry_mode", form.elements.geometry_mode.value);
  data.set("copies_mode", form.elements.copies_mode.value);
  data.set("set_name_mode", form.elements.set_name_mode.value);
  data.set("x_offset_delta", form.elements.x_offset_delta.value);
  data.set("y_offset_delta", form.elements.y_offset_delta.value);
  for (const file of sourcesInput.files) data.append("sources", file);
  if (templateInput.files[0]) data.set("template", templateInput.files[0]);
  return data;
}

function renderPreview(payload) {
  cards.className = "cards";
  cards.innerHTML = payload.items
    .map((item) => {
      const warnings = item.warnings.length
        ? item.warnings.map((warning) => `<div class="warning">${warning}</div>`).join("")
        : `<div class="ok">Sem alertas críticos para este arquivo.</div>`;

      return `
        <article class="card">
          <h3>${item.filename}</h3>
          <div class="meta">
            <div><strong>Origem:</strong> ${item.source.media_name || "N/D"}</div>
            <div><strong>Setup origem:</strong> ${item.source.last_base_setup_name || item.source.set_applied || "N/D"}</div>
            <div><strong>Template Atlas:</strong> ${payload.template.media_name || "N/D"}</div>
            <div><strong>Recomendação:</strong> <span class="rec-tag ${item.recommended_setup}">${item.recommended_setup.toUpperCase()}</span></div>
          </div>
          <div class="warnings">${warnings}</div>
        </article>
      `;
    })
    .join("");

  recommendationBox.classList.remove("empty");
  recommendationBox.innerHTML = payload.items
    .map((item) => {
      const firstWarning =
        item.warnings[0] || "Conversão pronta. Validar impressão física após o primeiro teste.";
      return `
        <div class="rec-item">
          <strong>${item.filename}</strong>
          <div>${firstWarning}</div>
          <span class="rec-tag ${item.recommended_setup}">${item.recommended_setup.toUpperCase()}</span>
        </div>
      `;
    })
    .join("");
}

async function callPreview() {
  updateHeader();
  if (!sourcesInput.files.length || !templateInput.files.length) {
    statusText.textContent = "Selecione origem e template";
    return;
  }
  statusText.textContent = "Analisando";
  const response = await fetch("/api/preview", {
    method: "POST",
    body: buildFormData(),
  });
  const payload = await response.json();
  if (!response.ok) {
    statusText.textContent = "Erro";
    alert(payload.error || "Falha ao analisar arquivos.");
    return;
  }
  renderPreview(payload);
  statusText.textContent = "Análise concluída";
}

previewBtn.addEventListener("click", () => {
  callPreview().catch((error) => {
    statusText.textContent = "Erro";
    alert(error.message);
  });
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  updateHeader();
  if (!sourcesInput.files.length || !templateInput.files.length) {
    statusText.textContent = "Selecione origem e template";
    return;
  }
  statusText.textContent = "Convertendo";
  const response = await fetch("/api/convert", {
    method: "POST",
    body: buildFormData(),
  });
  if (!response.ok) {
    let message = "Falha na conversão.";
    try {
      const payload = await response.json();
      message = payload.error || message;
    } catch (_) {}
    statusText.textContent = "Erro";
    alert(message);
    return;
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "atlas-max-converted.zip";
  a.click();
  URL.revokeObjectURL(url);
  statusText.textContent = "ZIP gerado";
});

sourcesInput.addEventListener("change", updateHeader);
templateInput.addEventListener("change", updateHeader);
updateHeader();
