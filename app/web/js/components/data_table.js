/** Generic data table component. */
function createDataTable(columns, options = {}) {
    const wrapper = document.createElement('div');
    wrapper.style.overflowX = 'auto';
    const table = document.createElement('table');
    table.className = 'data-table';
    if (options.id) table.id = options.id;

    const thead = document.createElement('thead');
    const headerRow = document.createElement('tr');
    columns.forEach(col => {
        const th = document.createElement('th');
        th.textContent = col.label;
        if (col.width) th.style.width = col.width;
        headerRow.appendChild(th);
    });
    thead.appendChild(headerRow);
    table.appendChild(thead);

    const tbody = document.createElement('tbody');
    table.appendChild(tbody);
    wrapper.appendChild(table);

    function setData(rows, onRowClick) {
        tbody.innerHTML = '';
        rows.forEach((row, idx) => {
            const tr = document.createElement('tr');
            if (row._class) tr.className = row._class;
            columns.forEach(col => {
                const td = document.createElement('td');
                if (col.class) td.className = col.class;
                td.textContent = col.render ? col.render(row) : (row[col.key] ?? '');
                if (col.html) td.innerHTML = col.html(row);
                tr.appendChild(td);
            });
            if (onRowClick) {
                tr.style.cursor = 'pointer';
                tr.addEventListener('click', () => onRowClick(row, idx, tr));
            }
            tbody.appendChild(tr);
        });
    }

    function selectRow(index) {
        tbody.querySelectorAll('tr').forEach((tr, i) => {
            tr.classList.toggle('selected', i === index);
        });
    }

    return { element: wrapper, table, tbody, setData, selectRow };
}
