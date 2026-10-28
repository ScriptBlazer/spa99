// System > Assistant > Overview: the test console. Posts the question, shows the reply and the exact knowledge sent. No streaming here.
const form = document.querySelector("[data-assistant-test]");
if (form) {
  const log = form.querySelector("[data-test-log]");
  const knowledge = form.querySelector("[data-test-knowledge]");
  const events = form.querySelector("[data-test-events]");
  const field = form.querySelector("textarea");
  const add = (who, text) => {
    const p = document.createElement("p");
    const label = document.createElement("span");
    label.className = "sa-who";
    label.textContent = who + " ";
    p.append(label, document.createTextNode(text));
    log.append(p);
  };
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const text = field.value.trim();
    if (!text) return;
    const data = new FormData(form);
    add("You", text);
    field.value = "";
    try {
      const response = await fetch(form.action, { method: "POST", body: data, credentials: "same-origin" });
      const body = await response.json();
      if (!response.ok) throw new Error(body.error || "Failed");
      form.querySelector("[name=conversation_id]").value = body.conversation_id;
      add("Assistant", body.text || "(no text)");
      knowledge.textContent = body.system;
      events.textContent = body.events.map((e) => e[0] + " " + JSON.stringify(e[1])).join("\n");
    } catch (error) {
      add("Error", String(error.message || error));
    }
  });
  form.querySelector("[data-test-reset]").addEventListener("click", () => {
    form.querySelector("[name=conversation_id]").value = "";
    log.replaceChildren();
  });
}
