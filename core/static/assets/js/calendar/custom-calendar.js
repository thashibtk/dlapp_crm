document.addEventListener('DOMContentLoaded', function () {
    var calendarEl = document.getElementById('calendar');
  
    var calendar = new FullCalendar.Calendar(calendarEl, {
      initialDate: '2020-09-12',
      initialView: 'timeGridWeek',
      headerToolbar: {
        left: 'prev,next today',
        center: 'title',
        right: 'dayGridMonth,timeGridWeek,timeGridDay,listWeek',
      }, 
      height: 'auto',
      navLinks: false, // can click day/week names to navigate views
      editable: true,
      selectable: true,
      selectMirror: true,
      nowIndicator: true,
      events: [
        {
          id: 1,
          task: 'Team Outing',
          hours: '08:00 AM - 09:30A',
          classNames: ['common-style', 'bg-white'],
          start: '2020-09-05T24:00:00',
          img: '13.png',
        }, 
        {
          id: 2,
          task: 'Design Meeting',
          hours: '08:00 AM - 09:30A', 
          classNames: ['common-style', 'bg-white'],
          start: '2020-09-07T01:00:00',
        }
      ],
    });
  
    calendar.render();
  });
  