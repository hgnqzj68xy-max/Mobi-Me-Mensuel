document.addEventListener('DOMContentLoaded', async () => {
  // Récupère le mois depuis l'URL ou utilise le mois courant
  const urlParams = new URLSearchParams(window.location.search);
  const month = urlParams.get('month') || new Date().toISOString().slice(0, 7);

  document.getElementById('month').textContent = month;

  // Charge les données
  const response = await fetch(`../data/${month}.json`);
  if (!response.ok) {
    document.getElementById('calendar').innerHTML = '<p>Aucune donnée disponible pour ce mois.</p>';
    return;
  }

  const data = await response.json();

  // Configure FullCalendar
  const calendarEl = document.getElementById('calendar');
  const calendar = new FullCalendar.Calendar(calendarEl, {
    initialView: 'dayGridMonth',
    locale: 'fr',
    events: data.games.map(game => ({
      title: game.name,
      start: game.date,
      url: game.url,
      extendedProps: {
        platform: game.platform,
      },
    })),
    eventDidMount: (info) => {
      const platform = info.event.extendedProps.platform.join(', ');
      info.el.setAttribute('title', `${info.event.title}\nPlateforme: ${platform}`);
    },
  });

  calendar.render();
});
