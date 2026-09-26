<script>
/* ============================================================
   AUTOCOMPLETADO DE BÚSQUEDA — ORION
   ============================================================ */
(function () {
    const input      = document.getElementById('searchInput');
    const form       = document.getElementById('searchForm');
    const dropdown   = document.getElementById('autocompleteResults');
    const list       = document.getElementById('autocompleteList');
    const loading    = document.getElementById('autocompleteLoading');
    const empty      = document.getElementById('autocompleteEmpty');
    const footer     = document.getElementById('autocompleteFooter');
    const verTodos   = document.getElementById('autocompleteVerTodos');

    if (!input || !dropdown) return;

    let debounceTimer = null;
    let controller    = null;
    let items         = [];
    let activeIndex   = -1;
    let currentQuery  = '';

    // ============================================================
    // UTILIDADES
    // ============================================================
    function escapeHtml(str) {
        if (!str) return '';
        return String(str)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#039;');
    }

    function escapeRegex(str) {
        return String(str).replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    }

    // Resalta las coincidencias del query en el nombre
    function highlight(text, query) {
        if (!query) return escapeHtml(text);
        const regex = new RegExp('(' + escapeRegex(query) + ')', 'gi');
        return escapeHtml(text).replace(regex, '<mark>$1</mark>');
    }

    function fmtPrecio(n) {
        return '$' + Number(n || 0).toFixed(2);
    }

    // ============================================================
    // MOSTRAR / OCULTAR DROPDOWN
    // ============================================================
    function showDropdown() {
        dropdown.style.display = 'block';
    }
    function hideDropdown() {
        dropdown.style.display = 'none';
        activeIndex = -1;
    }

    // ============================================================
    // RENDERIZADO
    // ============================================================
    function renderResults(resultados, query) {
        list.innerHTML = '';
        items = [];
        activeIndex = -1;

        if (!resultados || resultados.length === 0) {
            loading.style.display = 'none';
            empty.style.display   = 'block';
            footer.style.display  = 'none';
            list.style.display    = 'none';
            showDropdown();
            return;
        }

        loading.style.display = 'none';
        empty.style.display   = 'none';
        list.style.display    = 'block';
        footer.style.display  = 'block';
        list.innerHTML = '';

        resultados.forEach(function (p, idx) {
            const a = document.createElement('a');
            a.className = 'autocomplete-item';
            a.href = p.url;
            a.setAttribute('role', 'option');
            a.dataset.index = idx;

            const imgHtml = p.foto
                ? '<img src="' + escapeHtml(p.foto) + '" class="autocomplete-item-img" alt="" loading="lazy" onerror="this.style.display=\'none\'">'
                : '<div class="autocomplete-item-img placeholder"><i class="bi bi-image"></i></div>';

            const meta = [];
            if (p.marca)     meta.push('<span class="marca">' + escapeHtml(p.marca) + '</span>');
            if (p.categoria) meta.push('<span>' + escapeHtml(p.categoria) + '</span>');

            a.innerHTML =
                imgHtml +
                '<div class="autocomplete-item-info">' +
                    '<div class="autocomplete-item-name">' + highlight(p.nombre, query) + '</div>' +
                    '<div class="autocomplete-item-meta">' + meta.join('') + '</div>' +
                '</div>' +
                '<div class="autocomplete-item-price">' + fmtPrecio(p.precio) + '</div>';

            list.appendChild(a);
            items.push(a);
        });

        showDropdown();
    }

    // ============================================================
    // NAVEGACIÓN POR TECLADO
    // ============================================================
    function setActive(idx) {
        items.forEach(function (el) { el.classList.remove('active'); });
        if (idx < 0) { activeIndex = -1; return; }
        if (idx >= items.length) idx = 0;
        if (idx < 0) idx = items.length - 1;
        items[idx].classList.add('active');
        items[idx].scrollIntoView({ block: 'nearest' });
        activeIndex = idx;
    }

    input.addEventListener('keydown', function (e) {
        const isOpen = dropdown.style.display === 'block';

        if (e.key === 'ArrowDown') {
            if (!isOpen && currentQuery.length >= 2) {
                // Si el dropdown no está abierto y hay query, dispara búsqueda inmediata
                fetchSuggestions(currentQuery);
                e.preventDefault();
                return;
            }
            e.preventDefault();
            setActive(activeIndex + 1);
        } else if (e.key === 'ArrowUp') {
            if (isOpen) {
                e.preventDefault();
                setActive(activeIndex - 1);
            }
        } else if (e.key === 'Enter') {
            if (isOpen && activeIndex >= 0 && items[activeIndex]) {
                e.preventDefault();
                window.location.href = items[activeIndex].href;
            }
        } else if (e.key === 'Escape') {
            hideDropdown();
        }
    });

    // ============================================================
    // FETCH CON DEBOUNCE + ABORT
    // ============================================================
    function fetchSuggestions(query) {
        currentQuery = query;

        // Cancelar petición previa
        if (controller) {
            try { controller.abort(); } catch (e) {}
        }
        controller = new AbortController();

        loading.style.display = 'block';
        empty.style.display   = 'none';
        list.style.display    = 'none';
        footer.style.display  = 'none';
        showDropdown();

        const url = '/api/productos/autocompletar?q=' + encodeURIComponent(query);

        fetch(url, { signal: controller.signal })
            .then(function (r) { return r.json(); })
            .then(function (data) {
                if (!data || !data.success) throw new Error('Bad response');
                renderResults(data.resultados || [], query);
            })
            .catch(function (err) {
                if (err.name === 'AbortError') return; // Ignorar cancelaciones
                console.warn('Autocompletar error:', err);
                loading.style.display = 'none';
                empty.style.display   = 'block';
            });
    }

    // ============================================================
    // EVENTOS DEL INPUT
    // ============================================================
    input.addEventListener('input', function () {
        const q = input.value.trim();

        clearTimeout(debounceTimer);

        if (q.length < 2) {
            hideDropdown();
            return;
        }

        // Actualiza link "ver todos"
        if (verTodos) {
            verTodos.href = '/catalogo?q=' + encodeURIComponent(q);
        }

        debounceTimer = setTimeout(function () {
            fetchSuggestions(q);
        }, 220);
    });

    // ============================================================
    // CERRAR AL HACER CLIC FUERA
    // ============================================================
    document.addEventListener('click', function (e) {
        if (!dropdown.contains(e.target) && e.target !== input) {
            hideDropdown();
        }
    });

    // ============================================================
    // CERRAR AL SALIR DEL WRAPPER
    // ============================================================
    input.addEventListener('blur', function () {
        // Pequeño delay para permitir clic en resultados
        setTimeout(function () {
            if (!dropdown.matches(':hover')) hideDropdown();
        }, 180);
    });

    // ============================================================
    // MOSTRAR ÚLTIMA BÚSQUEDA AL RE-ENFOCAR
    // ============================================================
    input.addEventListener('focus', function () {
        const q = input.value.trim();
        if (q.length >= 2 && items.length > 0) {
            showDropdown();
        }
    });

    // ============================================================
    // EVITAR ENVÍO DE FORMULARIO AL NAVEGAR CON FLECHAS
    // ============================================================
    form.addEventListener('submit', function (e) {
        const isOpen = dropdown.style.display === 'block';
        if (isOpen && activeIndex >= 0 && items[activeIndex]) {
            e.preventDefault();
            window.location.href = items[activeIndex].href;
        }
    });

})();
</script>