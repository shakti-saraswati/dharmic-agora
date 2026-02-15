(() => {
    const filter = document.getElementById('queue-filter');
    const table = document.getElementById('queue-table');
    if (!filter || !table) return;

    filter.addEventListener('input', () => {
        const query = filter.value.toLowerCase();
        for (const row of table.tBodies[0].rows) {
            const text = row.innerText.toLowerCase();
            row.style.display = text.includes(query) ? '' : 'none';
        }
    });
})();
