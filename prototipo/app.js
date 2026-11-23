/* ============================================================
   Kotoduo Producción - interfaz contra la API real (Unidad 3)
   · Sesión con token Bearer guardado en el navegador.
   · Cada pantalla pide a la API sus datos; no hay datos simulados.
   · El menú y las acciones se habilitan según el rol (RBAC en el
     servidor manda: aquí solo se evita mostrar lo que no se puede usar).
   ============================================================ */
(function () {
  'use strict';

  var CLAVE = 'kotoduo_sesion';
  var PANTALLAS = ['p-login', 'p-operario', 'p-encargado', 'p-nuevo', 'p-vendedor', 'p-admin'];
  var INICIO = {
    operario: 'p-operario',
    encargado: 'p-encargado',
    vendedor: 'p-vendedor',
    administrador: 'p-admin'
  };
  var COLUMNAS = [
    { estado: 'en_diseño',     titulo: 'En diseño',     clase: 'violeta' },
    { estado: 'en_producción', titulo: 'En producción', clase: '' },
    { estado: 'detenido',      titulo: 'Detenidos',     clase: 'rojo' },
    { estado: 'terminado',     titulo: 'Terminados',    clase: 'verde' }
  ];
  var ETIQUETA_ESTADO = {
    'en_diseño': ['violeta', 'En diseño'],
    'en_producción': ['azul', 'En producción'],
    'detenido': ['rojo', 'Detenido'],
    'terminado': ['verde', 'Terminado'],
    'aprobado': ['verde', 'Aprobado'],
    'rechazado': ['rojo', 'Rechazado'],
    'pendiente': ['ambar', 'Pendiente'],
    'sin_version': ['gris', 'Sin versión']
  };

  var S = { token: null, usuario: null, nombre: null, rol: null };
  var disenosCargados = false;
  var avisoTimer = null;

  function $(id) { return document.getElementById(id); }

  function esc(v) {
    return String(v == null ? '' : v)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }

  function fechaCorta(f) {
    if (!f) return '—';
    var s = String(f);
    if (s.length >= 10 && s.indexOf('-') === 4) {
      return s.slice(8, 10) + '-' + s.slice(5, 7) + '-' + s.slice(0, 4);
    }
    return s;
  }

  function horaCorta(f) {
    if (!f) return '';
    var s = String(f);
    return s.length >= 16 ? s.slice(8, 10) + '-' + s.slice(5, 7) + ' ' + s.slice(11, 16) : s;
  }

  function etiqueta(clave) {
    var e = ETIQUETA_ESTADO[clave] || ['gris', clave];
    return '<span class="etiqueta ' + e[0] + '">' + esc(e[1]) + '</span>';
  }

  function inicialiales(nombre) {
    var p = String(nombre || '').trim().split(/\s+/);
    return ((p[0] || '?')[0] + (p[1] ? p[1][0] : '')).toUpperCase();
  }

  /* ------------------------------------------------------ avisos */
  function toast(msg, tipo) {
    var t = $('toast');
    t.textContent = msg;
    t.className = 'toast' + (tipo ? ' ' + tipo : '');
    t.hidden = false;
    requestAnimationFrame(function () { t.classList.add('visible'); });
    clearTimeout(avisoTimer);
    avisoTimer = setTimeout(function () {
      t.classList.remove('visible');
      setTimeout(function () { t.hidden = true; }, 240);
    }, 2800);
  }

  /* ------------------------------------------------------ cliente de la API */
  function mensajeError(status, datos) {
    if (datos && datos.detail) {
      if (Array.isArray(datos.detail)) {
        return datos.detail.map(function (d) { return d.msg || JSON.stringify(d); }).join('; ');
      }
      return String(datos.detail);
    }
    var mapa = {
      401: 'Sin sesión o sesión expirada',
      403: 'Tu rol no tiene permiso para esta acción',
      404: 'No se encontró lo pedido',
      409: 'Conflicto: revisa el estado actual',
      422: 'Revisa los campos ingresados',
      500: 'Error interno del servidor'
    };
    return mapa[status] || ('Error ' + status);
  }

  async function api(ruta, opciones) {
    var opts = opciones || {};
    var cab = { 'Accept': 'application/json' };
    Object.keys(opts.headers || {}).forEach(function (k) { cab[k] = opts.headers[k]; });
    if (S.token) cab['Authorization'] = 'Bearer ' + S.token;
    if (opts.body !== undefined && typeof opts.body !== 'string') {
      cab['Content-Type'] = 'application/json';
      opts.body = JSON.stringify(opts.body);
    }
    opts.headers = cab;
    var r = await fetch(ruta, opts);
    var datos = null;
    try { datos = await r.json(); } catch (e) { /* sin cuerpo JSON */ }
    if (r.status === 401) {
      cerrarSesion(true);
      throw new Error('Sesión expirada: vuelve a iniciar sesión');
    }
    if (!r.ok) {
      var err = new Error(mensajeError(r.status, datos));
      err.status = r.status;
      throw err;
    }
    return datos;
  }

  /* ------------------------------------------------------ navegación */
  function mostrar(id) {
    PANTALLAS.forEach(function (p) {
      var el = $(p);
      if (el) el.classList.toggle('activa', p === id);
    });
    document.querySelectorAll('#nav button[data-pantalla]').forEach(function (b) {
      b.classList.toggle('activo', b.getAttribute('data-pantalla') === id);
    });
    if (id === 'p-operario') cargarOperario();
    if (id === 'p-encargado') cargarEncargado();
    if (id === 'p-nuevo') prepararNuevo();
    if (id === 'p-admin') cargarAdmin();
    if (id === 'p-vendedor' && !$('resultado').children.length) estadoVacioPedido();
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  function pintarNav() {
    document.querySelectorAll('#nav button[data-rol]').forEach(function (b) {
      b.hidden = b.getAttribute('data-rol').split(' ').indexOf(S.rol) === -1;
    });
  }

  function guardarSesion() {
    try { localStorage.setItem(CLAVE, JSON.stringify(S)); } catch (e) { /* modo privado */ }
  }

  function leerSesion() {
    try {
      var crudo = localStorage.getItem(CLAVE);
      if (crudo) S = JSON.parse(crudo);
    } catch (e) { S = { token: null }; }
  }

  function iniciarSesion() {
    $('sesion').textContent = S.nombre + ' · ' + S.rol;
    ['op-avatar', 'ven-avatar'].forEach(function (id) {
      if ($(id)) $(id).textContent = inicialiales(S.nombre);
    });
    $('nav').hidden = false;
    pintarNav();
    mostrar(INICIO[S.rol] || 'p-login');
  }

  function cerrarSesion(silencioso) {
    S = { token: null, usuario: null, nombre: null, rol: null };
    try { localStorage.removeItem(CLAVE); } catch (e) { /* nada */ }
    $('nav').hidden = true;
    $('sesion').textContent = '';
    mostrar('p-login');
    if (!silencioso) toast('Sesión cerrada');
  }

  /* ------------------------------------------------------ estados auxiliares */
  function vacio(titulo, texto) {
    return '<div class="vacio"><b>' + esc(titulo) + '</b>' + esc(texto) + '</div>';
  }

  function panelError(msg) {
    return '<div class="error-panel">' + esc(msg) + '</div>';
  }

  function cargando(caja, activo) {
    var c = $(caja);
    if (c) c.hidden = !activo;
  }

  /* ------------------------------------------------------ Login */
  async function entrarCon(usuario, password) {
    var d = await api('/auth/login', {
      method: 'POST',
      body: { usuario: usuario, password: password }
    });
    S = { token: d.token, usuario: d.usuario, nombre: d.nombre, rol: d.rol };
    guardarSesion();
    $('login-error').hidden = true;
    iniciarSesion();
  }

  $('f-login').addEventListener('submit', async function (e) {
    e.preventDefault();
    S.token = null;
    try {
      await entrarCon($('i-usuario').value.trim(), $('i-clave').value);
    } catch (err) {
      var caja = $('login-error');
      caja.textContent = err.message;
      caja.hidden = false;
      toast(err.message, 'error');
    }
  });

  document.querySelectorAll('.link[data-user]').forEach(function (b) {
    b.addEventListener('click', function () {
      var partes = b.getAttribute('data-user').split('|');
      $('i-usuario').value = partes[0];
      $('i-clave').value = partes[1];
      $('f-login').dispatchEvent(new Event('submit', { cancelable: true }));
    });
  });

  $('btn-salir').addEventListener('click', function () { cerrarSesion(false); });

  document.querySelectorAll('#nav button[data-pantalla]').forEach(function (b) {
    b.addEventListener('click', function () { mostrar(b.getAttribute('data-pantalla')); });
  });

  /* ------------------------------------------------------ Operario (HU-01/HU-02) */
  function tarjetaTarea(d) {
    return '' +
      '<article class="tarjeta" id="tar-tarea">' +
        '<div class="titular">' +
          etiqueta('en_producción').replace('En producción', esc(d.etapa)) +
          '<span class="etiqueta gris">Etapa ' + d.orden + ' de ' + d.total_etapas + '</span>' +
        '</div>' +
        '<h2>' + esc(d.codigo) + ' · ' + esc(d.cliente_etiqueta) + '</h2>' +
        '<p class="meta">' + d.unidades + ' unidades · área ' + esc(d.area) +
          ' · compromiso ' + fechaCorta(d.fecha_compromiso) + '</p>' +
        '<details>' +
          '<summary>Medidas y materiales</summary>' +
          '<ul>' +
            '<li>Medidas: ' + esc(d.medidas) + '</li>' +
            '<li>Área de trabajo: ' + esc(d.area) + '</li>' +
            '<li>Unidades del pedido: ' + d.unidades + '</li>' +
            '<li>Etapa ' + d.orden + ' de ' + d.total_etapas + '</li>' +
          '</ul>' +
        '</details>' +
        '<button class="btn ancho" id="btn-avance" data-cerrar="' + d.etapa_trabajo_id + '">' +
          'Registrar avance</button>' +
      '</article>' +
      '<article class="tarjeta fantasma">' +
        '<span class="etiqueta gris">Sin más etapas asignadas</span>' +
        '<p>Cuando la encargada te asigne una nueva tarea aparecerá aquí.</p>' +
      '</article>';
  }

  async function cargarOperario() {
    cargando('op-carga', true);
    var caja = $('op-lista');
    caja.innerHTML = '';
    try {
      var d = await api('/trabajos/siguiente');
      caja.innerHTML = (d && d.codigo)
        ? tarjetaTarea(d)
        : vacio('Sin etapas abiertas', 'Cuando la encargada te asigne una nueva tarea aparecerá aquí.');
    } catch (e) {
      caja.innerHTML = panelError(e.message);
    } finally {
      cargando('op-carga', false);
    }
  }

  /* ------------------------------------------------------ Encargado (HU-05/HU-04/HU-06) */
  function pintarKpis(conteos) {
    var datos = [
      { estado: 'en_diseño', titulo: 'En diseño', clase: 'violeta' },
      { estado: 'en_producción', titulo: 'En producción', clase: '' },
      { estado: 'detenido', titulo: 'Detenidos', clase: 'rojo' },
      { estado: 'terminado', titulo: 'Terminados', clase: 'verde' }
    ];
    $('kpis').innerHTML = datos.map(function (k) {
      return '<div class="kpi ' + k.clase + '"><b>' + (conteos[k.estado] || 0) +
             '</b><span>' + k.titulo + '</span></div>';
    }).join('');
  }

  function tarjetaTrabajo(t) {
    var hoy = new Date().toISOString().slice(0, 10);
    var atrasado = t.fecha_compromiso && t.fecha_compromiso < hoy && t.estado_general !== 'terminado';
    var lineas = [];
    lineas.push('<div class="linea-mini"><b>' + esc(t.codigo) + '</b>' +
      (t.etapa_actual ? etiqueta('en_producción').replace('En producción', esc(t.etapa_actual)) : etiqueta('terminado')) +
      '</div>');
    lineas.push('<p>' + esc(t.cliente_etiqueta) + (t.responsable ? ' · ' + esc(t.responsable) : '') + '</p>');
    lineas.push('<div class="linea-mini"><span class="meta">Compromiso ' +
      fechaCorta(t.fecha_compromiso) + (atrasado ? ' · <b style="color:#DC2626">atrasado</b>' : '') + '</span>' +
      (t.etapa_trabajo_id && t.estado_general !== 'terminado'
        ? '<button class="btn chico secundario" data-cerrar="' + t.etapa_trabajo_id + '">Cerrar etapa</button>'
        : '') +
      '</div>');
    return '<article class="tarjeta mini' + (atrasado ? ' alerta' : '') + '">' + lineas.join('') + '</article>';
  }

  function pintarTablero(trabajos) {
    $('tablero').innerHTML = COLUMNAS.map(function (col) {
      var lista = trabajos.filter(function (t) { return t.estado_general === col.estado; });
      var cuerpo = lista.length
        ? lista.map(tarjetaTrabajo).join('')
        : '<p class="col-vacia">Sin trabajos en este estado</p>';
      return '<div class="col"><h3>' + col.titulo +
        '<span class="conteo ' + col.clase + '">' + lista.length + '</span></h3>' + cuerpo + '</div>';
    }).join('');
  }

  function pintarAlertas(alertas) {
    var caja = $('alertas');
    $('alert-punto').hidden = !alertas.length;
    caja.innerHTML = alertas.length
      ? alertas.map(function (a) {
          return '<article class="tarjeta alerta">' +
            '<span class="etiqueta rojo">Bajo umbral</span>' +
            '<p><b>' + esc(a.nombre) + ':</b> ' + a.stock_actual + ' disponible ' +
            '(umbral ' + a.umbral_minimo + '). Avisado a encargado y vendedor.</p>' +
            '</article>';
        }).join('')
      : vacio('Sin alertas de insumos', 'Todos los insumos están por sobre su umbral mínimo.');
  }

  async function cargarEncargado() {
    cargando('tab-carga', true);
    try {
      var res = await Promise.all([
        api('/tablero'),
        api('/trabajos'),
        api('/insumos/alertas')
      ]);
      pintarKpis(res[0]);
      pintarTablero(res[1]);
      pintarAlertas(res[2]);
      $('dis-punto').hidden = !res[1].some(function (t) { return t.estado_general === 'en_diseño'; });
      await pintarSelectorDisenos(res[1]);
    } catch (e) {
      $('tablero').innerHTML = panelError(e.message);
    } finally {
      cargando('tab-carga', false);
    }
  }

  async function pintarSelectorDisenos(trabajos) {
    var sel = $('dis-trabajo');
    var previo = sel.value;
    sel.innerHTML = trabajos.map(function (t) {
      return '<option value="' + esc(t.codigo) + '">' + esc(t.codigo) + ' · ' +
             esc(t.cliente_etiqueta) + '</option>';
    }).join('');
    if (previo && trabajos.some(function (t) { return t.codigo === previo; })) sel.value = previo;
    disenosCargados = false;
    if ($('seg-disenos').classList.contains('activo')) await cargarDisenos();
  }

  function fichaDiseno(d) {
    var cod = d.codigo || $('dis-trabajo').value;
    var detalle = [];
    if (d.paleta && d.paleta.length) detalle.push('Paleta: ' + d.paleta.join(', '));
    if (d.variantes && d.variantes.length) {
      detalle.push(d.variantes.length + ' variante(s): ' +
        d.variantes.map(function (v) { return v.nombre + ' (' + v.medidas + ')'; }).join(' · '));
    }
    if (d.decidido_por) detalle.push('Decidido por ' + d.decidido_por);
    var acciones = '';
    if (d.estado === 'pendiente') {
      acciones = '<div class="fila-acciones" style="margin-top:.8rem;justify-content:flex-start">' +
        '<button class="btn chico" data-decision="aprobado" data-codigo="' + esc(cod) +
          '" data-version="' + d.version + '">Aprobar</button>' +
        '<button class="btn chico peligro" data-decision="rechazado" data-codigo="' + esc(cod) +
          '" data-version="' + d.version + '">Rechazar</button>' +
        '</div>';
    }
    return '<article class="tarjeta">' +
      '<div class="titular">' + etiqueta(d.estado) +
        '<span class="meta">v' + d.version + ' · ' + fechaCorta(d.fecha) + '</span></div>' +
      '<h2>' + esc(d.archivo || 'Sin archivo cargado') + '</h2>' +
      (d.formato ? '<p class="meta">Formato ' + esc(d.formato) + (detalle.length ? ' · ' + esc(detalle.join(' · ')) : '') + '</p>' : '') +
      (d.comentarios ? '<p>' + esc(d.comentarios) + '</p>' : '') +
      (d.observaciones && d.observaciones.length
        ? '<ul class="meta" style="margin:.4rem 0 0;padding-left:1.1rem">' +
          d.observaciones.map(function (o) { return '<li>' + esc(o) + '</li>'; }).join('') + '</ul>'
        : '') +
      acciones +
      '</article>';
  }

  async function cargarDisenos() {
    var codigo = $('dis-trabajo').value;
    var caja = $('dis-lista');
    if (!codigo) {
      caja.innerHTML = vacio('Sin trabajos', 'Crea un trabajo para gestionar su diseño.');
      return;
    }
    cargando('dis-carga', true);
    caja.innerHTML = '';
    try {
      var lista = await api('/trabajos/' + encodeURIComponent(codigo) + '/disenos');
      disenosCargados = true;
      caja.innerHTML = lista.length
        ? '<div class="titular" style="margin-bottom:.2rem"><h2>Diseños de ' + esc(codigo) + '</h2></div>' +
          lista.map(fichaDiseno).join('')
        : vacio('Sin versiones de diseño', 'Sube la primera versión para enviarla a aprobación.');
    } catch (e) {
      caja.innerHTML = panelError(e.message);
    } finally {
      cargando('dis-carga', false);
    }
  }

  /* ------------------------------------------------------ Nuevo trabajo (HU-03) */
  function siguienteCodigo(trabajos) {
    var max = 0;
    trabajos.forEach(function (t) {
      var m = /KTO-2026-(\d{3})/.exec(t.codigo);
      if (m) max = Math.max(max, parseInt(m[1], 10));
    });
    return 'KTO-2026-' + String(max + 1).padStart(3, '0');
  }

  async function prepararNuevo() {
    if ($('t-codigo').value) return;
    try {
      var trabajos = await api('/trabajos');
      $('t-codigo').value = siguienteCodigo(trabajos);
    } catch (e) { /* se completa a mano */ }
  }

  $('f-trabajo').addEventListener('submit', async function (e) {
    e.preventDefault();
    var cuerpo = {
      codigo: $('t-codigo').value.trim().toUpperCase(),
      tipo_trabajo: $('t-tipo').value,
      cliente_etiqueta: $('t-cliente').value.trim(),
      pedido_ref: $('t-pedido').value.trim() || null,
      unidades: parseInt($('t-unidades').value, 10),
      medidas: $('t-medidas').value.trim(),
      fecha_compromiso: $('t-fecha').value || null
    };
    try {
      var d = await api('/trabajos', { method: 'POST', body: cuerpo });
      toast('Trabajo ' + d.codigo + ' creado y enviado a diseño', 'ok');
      $('f-trabajo').reset();
      $('t-codigo').value = '';
      disenosCargados = false;
      mostrar('p-encargado');
    } catch (err) {
      toast(err.message, 'error');
    }
  });

  $('btn-nuevo').addEventListener('click', function () {
    $('t-codigo').value = '';
    mostrar('p-nuevo');
  });
  $('t-cancelar').addEventListener('click', function () { mostrar('p-encargado'); });

  /* ------------------------------------------------------ Vendedor (HU-08) */
  function estadoVacioPedido() {
    $('resultado').innerHTML =
      vacio('Sin consultas todavía', 'Escribe un código de trabajo, por ejemplo KTO-2026-015.');
  }

  async function buscarPedido(codigo) {
    var caja = $('resultado');
    if (!/^KTO-2026-\d{3}$/.test(codigo)) {
      toast('El código tiene el formato KTO-2026-000', 'error');
      return;
    }
    cargando('ven-carga', true);
    caja.innerHTML = '';
    try {
      var d = await api('/trabajos/' + encodeURIComponent(codigo) + '/estado');
      var pct = d.total_etapas ? Math.round(100 * d.etapas_cerradas / d.total_etapas) : 0;
      caja.innerHTML =
        '<article class="tarjeta">' +
          '<div class="titular">' + etiqueta(d.estado_general) + etiqueta(d.diseno) +
            '<span class="meta">' + esc(d.pedido_ref || 'Sin referencia') + '</span></div>' +
          '<h2>' + esc(d.codigo) + ' · ' + esc(d.cliente_etiqueta) + '</h2>' +
          '<p>Etapa actual: <b>' + esc(d.etapa_actual || 'Sin etapa abierta') + '</b>' +
            (d.responsable ? ' · responsable <b>' + esc(d.responsable) + '</b>' : '') +
            ' · ' + d.etapas_cerradas + ' de ' + d.total_etapas + ' etapas cerradas' +
            ' · Compromiso: ' + fechaCorta(d.fecha_compromiso) + '.</p>' +
          '<div class="progreso"><i style="width:' + pct + '%"></i></div>' +
          '<p class="progreso-texto">' + pct + '% del trabajo completado · ' +
            d.unidades + ' unidades · ' + esc(d.medidas) + '</p>' +
          '<p class="meta">Diseño ' + (d.diseno === 'sin_version' ? 'sin versiones' :
            'v' + d.diseno_version + ' ' + d.diseno) + ' · tipo ' + esc(d.tipo_trabajo) + '</p>' +
          '<p class="nota">Sin montos ni datos de contacto: solo estado operativo.</p>' +
        '</article>';
    } catch (err) {
      caja.innerHTML = panelError(err.message);
      toast(err.message, 'error');
    } finally {
      cargando('ven-carga', false);
    }
  }

  $('f-buscar').addEventListener('submit', function (e) {
    e.preventDefault();
    buscarPedido($('b-codigo').value.trim().toUpperCase());
  });

  /* ------------------------------------------------------ Administrador (HU-07) */
  function filaUsuario(u, yo) {
    var mio = u.usuario === yo;
    var roles = ['operario', 'encargado', 'vendedor', 'administrador'];
    return '<tr>' +
      '<td><b>' + esc(u.usuario) + '</b></td>' +
      '<td>' + esc(u.nombre) + '</td>' +
      '<td><select class="en-tabla" data-rol-de="' + u.id + '"' + (mio ? ' disabled' : '') + '>' +
        roles.map(function (r) {
          return '<option value="' + r + '"' + (r === u.rol ? ' selected' : '') + '>' +
                 r.charAt(0).toUpperCase() + r.slice(1) + '</option>';
        }).join('') + '</select></td>' +
      '<td><span class="badge-estado ' + (u.activo ? 'on">Activo' : 'off">Inactivo') + '</span></td>' +
      '<td class="der"><div class="fila-acciones">' +
        (mio
          ? '<span class="meta">tu cuenta</span>'
          : '<button class="btn chico ' + (u.activo ? 'peligro' : 'secundario') +
            '" data-toggle-usuario="' + u.id + '" data-activo="' + (u.activo ? 0 : 1) + '">' +
            (u.activo ? 'Desactivar' : 'Activar') + '</button>') +
      '</div></td></tr>';
  }

  function filaBitacora(b) {
    return '<tr>' +
      '<td>' + esc(horaCorta(b.fecha)) + '</td>' +
      '<td>' + esc(b.nombre) + '</td>' +
      '<td><span class="etiqueta gris">' + esc(b.accion) + '</span></td>' +
      '<td>' + esc(b.entidad) + (b.entidad_id ? ' #' + b.entidad_id : '') + '</td>' +
      '<td>' + esc((b.valor_anterior || '—') + ' → ' + (b.valor_posterior || '—')) + '</td>' +
      '</tr>';
  }

  async function cargarAdmin() {
    try {
      var res = await Promise.all([api('/usuarios'), api('/bitacora')]);
      $('tabla-usuarios').innerHTML = res[0].length
        ? res[0].map(function (u) { return filaUsuario(u, S.usuario); }).join('')
        : '<tr class="tabla-vacia"><td colspan="5">Sin usuarios registrados</td></tr>';
      $('tabla-bitacora').innerHTML = res[1].length
        ? res[1].map(filaBitacora).join('')
        : '<tr class="tabla-vacia"><td colspan="5">Sin movimientos registrados</td></tr>';
    } catch (e) {
      $('tabla-usuarios').innerHTML =
        '<tr class="tabla-vacia"><td colspan="5">' + esc(e.message) + '</td></tr>';
    }
  }

  $('adm-nuevo').addEventListener('click', function () {
    var f = $('f-usuario');
    f.hidden = !f.hidden;
    if (!f.hidden) $('u-usuario').focus();
  });
  $('u-cancelar').addEventListener('click', function () { $('f-usuario').hidden = true; });

  $('f-usuario').addEventListener('submit', async function (e) {
    e.preventDefault();
    try {
      var d = await api('/usuarios', {
        method: 'POST',
        body: {
          usuario: $('u-usuario').value.trim().toLowerCase(),
          nombre: $('u-nombre').value.trim(),
          password: $('u-clave').value,
          rol: $('u-rol').value
        }
      });
      toast('Usuario ' + d.usuario + ' creado (' + d.rol + ')', 'ok');
      $('f-usuario').reset();
      $('f-usuario').hidden = true;
      cargarAdmin();
    } catch (err) {
      toast(err.message, 'error');
    }
  });

  /* ------------------------------------------------------ Acciones delegadas */
  document.addEventListener('click', async function (ev) {
    var btn = ev.target.closest('[data-cerrar], [data-decision], [data-toggle-usuario]');
    if (!btn) return;
    ev.preventDefault();

    if (btn.hasAttribute('data-cerrar')) {
      btn.disabled = true;
      try {
        var r = await api('/etapas/' + btn.getAttribute('data-cerrar') + '/cerrar',
                          { method: 'POST' });
        toast('Etapa cerrada: ' + r.trabajo + ' · ' + r.estado_trabajo, 'ok');
        if (S.rol === 'operario') cargarOperario(); else cargarEncargado();
      } catch (e) {
        toast(e.message, 'error');
        btn.disabled = false;
      }
      return;
    }

    if (btn.hasAttribute('data-decision')) {
      btn.disabled = true;
      try {
        var cod = btn.getAttribute('data-codigo') || $('dis-trabajo').value;
        var ver = btn.getAttribute('data-version');
        var est = btn.getAttribute('data-decision');
        await api('/trabajos/' + encodeURIComponent(cod) + '/disenos/' + ver + '/decision', {
          method: 'POST',
          body: { estado: est, comentarios: est === 'aprobado'
            ? 'Diseño aprobado desde la interfaz' : 'Diseño rechazado desde la interfaz' }
        });
        toast('Diseño v' + ver + ' ' + est + ' (' + cod + ')', est === 'aprobado' ? 'ok' : 'error');
        cargarDisenos();
        cargarEncargado();
      } catch (e) {
        toast(e.message, 'error');
        btn.disabled = false;
      }
      return;
    }

    if (btn.hasAttribute('data-toggle-usuario')) {
      btn.disabled = true;
      try {
        var activo = btn.getAttribute('data-activo') === '1';
        var id = btn.getAttribute('data-toggle-usuario');
        await api('/usuarios/' + id, { method: 'PATCH', body: { activo: activo } });
        toast(activo ? 'Usuario activado' : 'Usuario desactivado', 'ok');
        cargarAdmin();
      } catch (e) {
        toast(e.message, 'error');
        btn.disabled = false;
      }
    }
  });

  document.addEventListener('change', async function (ev) {
    var sel = ev.target;
    if (sel.matches('select[data-rol-de]')) {
      try {
        await api('/usuarios/' + sel.getAttribute('data-rol-de'),
                  { method: 'PATCH', body: { rol: sel.value } });
        toast('Rol actualizado a ' + sel.value, 'ok');
        cargarAdmin();
      } catch (e) {
        toast(e.message, 'error');
        cargarAdmin();
      }
      return;
    }
    if (sel.id === 'dis-trabajo' && disenosCargados !== false) cargarDisenos();
  });

  /* ------------------------------------------------------ Segmentos y formularios */
  document.querySelectorAll('.segmento').forEach(function (s) {
    s.addEventListener('click', function () {
      document.querySelectorAll('.segmento').forEach(function (o) {
        o.classList.toggle('activo', o === s);
        o.setAttribute('aria-selected', o === s ? 'true' : 'false');
      });
      document.querySelectorAll('.segmento-panel').forEach(function (p) {
        var activo = p.id === s.getAttribute('data-seg');
        p.classList.toggle('activo', activo);
        p.hidden = !activo;
      });
      if (s.getAttribute('data-seg') === 'seg-disenos') cargarDisenos();
      if (s.getAttribute('data-seg') === 'seg-alertas') cargarEncargado();
    });
  });

  $('dis-nueva').addEventListener('click', function () {
    var f = $('f-diseno');
    f.hidden = !f.hidden;
    if (!f.hidden) $('d-archivo').focus();
  });
  $('dis-cancelar').addEventListener('click', function () { $('f-diseno').hidden = true; });

  $('f-diseno').addEventListener('submit', async function (e) {
    e.preventDefault();
    var codigo = $('dis-trabajo').value;
    if (!codigo) { toast('Elige un trabajo primero', 'error'); return; }
    var archivo = $('d-archivo').value.trim();
    var variante = $('d-variante').value.trim();
    var partes = variante ? variante.split(/\s+(?=[\d])/) : [];
    try {
      await api('/trabajos/' + encodeURIComponent(codigo) + '/disenos', {
        method: 'POST',
        body: {
          archivo: archivo,
          formato: $('d-formato').value,
          paleta: $('d-paleta').value.split(',').map(function (x) { return x.trim(); })
                    .filter(Boolean),
          variantes: partes.length >= 2
            ? [{ nombre: partes[0], medidas: partes.slice(1).join(' '),
                 archivo: archivo.split('/').pop() }]
            : [],
          observaciones: $('d-obs').value.trim() ? [$('d-obs').value.trim()] : []
        }
      });
      toast('Versión subida a ' + codigo + ': pendiente de aprobación', 'ok');
      $('f-diseno').reset();
      $('f-diseno').hidden = true;
      cargarDisenos();
    } catch (err) {
      toast(err.message, 'error');
    }
  });

  /* ------------------------------------------------------ Arranque */
  leerSesion();
  if (S.token) iniciarSesion(); else mostrar('p-login');
})();
