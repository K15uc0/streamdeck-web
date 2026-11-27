/* Stream Deck - service worker da extensao (Manifest V3). A logica fica em ponte.js. */
/* global importScripts, criarPonte, chrome */
importScripts("ponte.js");

var ponte = criarPonte(chrome, fetch.bind(self));
var pronto = ponte.load().then(function () { ponte.start(); });

function mudou() { pronto.then(ponte.tabsChanged); }
chrome.tabs.onCreated.addListener(mudou);
chrome.tabs.onRemoved.addListener(mudou);
chrome.tabs.onActivated.addListener(mudou);
chrome.tabs.onUpdated.addListener(function (id, info) {
  if (info.title !== undefined || info.url !== undefined || info.audible !== undefined || info.status === "complete") mudou();
});
chrome.windows.onFocusChanged.addListener(mudou);
chrome.runtime.onStartup.addListener(function () { pronto.then(ponte.start); });
chrome.runtime.onInstalled.addListener(function () { pronto.then(ponte.start); });

/* popup: {type: "status" | "pair" | "unpair"} */
chrome.runtime.onMessage.addListener(function (msg, sender, reply) {
  if (sender.id !== chrome.runtime.id) return false;
  pronto.then(function () {
    if (msg.type === "pair") return ponte.pair(msg.code, msg.port || null);
    if (msg.type === "unpair") return ponte.unpair();
    ponte.start();
    return ponte.status();
  }).then(function (s) { reply({ ok: true, status: s }); },
          function (e) { reply({ ok: false, error: e.message, status: ponte.status() }); });
  return true;
});
