// ── PWA Service Worker ──
if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js').catch(() => {});
  });
}

// ── Lembretes (notificações browser) ──
async function verificarLembretes() {
  try {
    const resp = await fetch('/api/lembretes');
    const limpezas = await resp.json();
    if (!limpezas.length) return;

    // Banner na página
    const banner = document.getElementById('lembrete-banner');
    const texto = document.getElementById('lembrete-texto');
    if (banner && texto) {
      const nomes = limpezas.map(l => `${l.cliente} às ${l.data_hora}`).join(' | ');
      texto.textContent = nomes;
      banner.classList.remove('d-none');
    }

    // Notificações do browser (se permitido)
    if (Notification.permission === 'granted') {
      limpezas.forEach(l => {
        const jaNotificado = sessionStorage.getItem(`notif_${l.id}`);
        if (!jaNotificado) {
          new Notification(`🧹 Limpeza em breve: ${l.cliente}`, {
            body: `${l.data_hora} (${l.minutos < 60 ? l.minutos + ' min' : Math.round(l.minutos/60) + 'h'})`,
            icon: '/static/icons/icon-192.png',
            tag: `limpeza-${l.id}`
          });
          sessionStorage.setItem(`notif_${l.id}`, '1');
        }
      });
    }
  } catch (e) {}
}

async function pedirPermissaoNotificacoes() {
  if (!('Notification' in window)) return;
  if (Notification.permission === 'default') {
    const perm = await Notification.requestPermission();
    if (perm === 'granted') verificarLembretes();
  }
}

// Iniciar ao carregar a página
window.addEventListener('DOMContentLoaded', () => {
  verificarLembretes();
  // verificar a cada hora
  setInterval(verificarLembretes, 60 * 60 * 1000);
  // Pedir permissão de notificações só após interação do utilizador
  document.addEventListener('click', function pedirUmaVez() {
    pedirPermissaoNotificacoes();
    document.removeEventListener('click', pedirUmaVez);
  }, { once: true });
});
