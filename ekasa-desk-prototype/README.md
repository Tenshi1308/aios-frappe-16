# Ekasa Desk — clickable prototype

Open `index.html` in a browser (needs internet for Vue 3.4.21 from jsDelivr and Google Fonts).

- Boot screen → sign-in (any password) → desktop
- Ctrl K: search · Ctrl J: AI agents · Esc: close flyouts
- Agent replies are simulated in `agentReply()`; in production replace with a call to
  `frappe.call('ekasa.api.agent.chat', {agent, message, context})`.
