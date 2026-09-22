// Copy this file to vike-config.js (gitignored) and fill in your real
// values. vike-config.js is loaded by index.html and is never committed,
// so the bot token doesn't end up in git history — though note it still
// ships to every visitor's browser once deployed, since this is a
// client-side call. For real protection from a public token, route the
// notification through a server-side proxy (serverless function) instead.
window.VIKE_TELEGRAM_CONFIG = {
  botToken: 'YOUR_BOT_TOKEN_HERE',
  chatIds: ['YOUR_CHAT_ID_HERE']
};
