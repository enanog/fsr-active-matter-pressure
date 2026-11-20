function E = cargar_datos(ensayos, duracion_s)
% CARGAR_DATOS  Lee los ensayos cuyo código contiene alguno de los textos de ENSAYOS ({} = elegir de una lista),
% solo DURACION_S segundos desde el fin de la última señal del LED (Inf = todo): el video ya empieza ahí (t_video = 0)
% y del sensor se guardan solo las muestras con t_sensor en [desfase, desfase + DURACION_S]. Una fila de E por ensayo:
%   E.codigo    código de la medición (igual que R_<código>.csv y VP_<código>_robots.csv)
%   E.t, E.V    tiempo de video de cada cuadro [s reales] y V media del conjunto en ese cuadro [mm/s]
%   E.nf        cantidad de cuadros
%   E.omega     ω de cada robot observado en cada cuadro [°/s] (> 0 antihorario; sin interpolados)
%   E.x, E.y    posición de cada robot en cada cuadro [mm], origen en el centro del recinto
%   E.ts, E.G   sensor: grilla de tiempo [s del sensor] y G [µS], NaN fuera de lo analizado ([] si no hay log)
%   E.G_cuadro  G en el instante de cada cuadro [µS] (t_sensor = desfase + t_video)
%   E.paso, E.desfase, E.K   paso de la grilla [s], desfase video-sensor [s], factor [µS/cuenta]
%   E.R_lista     R_FEEDBACK [ohm] de datos/presion/calibracion.csv: la única que se usa para G
%   E.R_firmware  R_FEEDBACK [ohm] con la que calculó el firmware (de G/ADC del log), solo para comparar
% R = cargar_datos('R_feedback') devuelve la tabla R_lista vs R_firmware de todos los registros
% (datos/presion/crudos).
% exportar = cargar_datos('exportar') devuelve una función para guardar figuras: exportar(fig, base, formatos, dpi),
% con formatos = {'.png', '.pdf', ...} (ver la función exportar al final).
% estilos = cargar_datos('estilos'): [colores, lineas, marcas] = estilos(E, linea_por_modo), un color por ensayo
% dentro de la familia de su modo (AH azules, HO verdes, AL rojos/naranjas) y trazo/marcador por modo.
% leyenda = cargar_datos('leyenda'): leyenda(ax) arma la leyenda agrupada por modo, con un encabezado por grupo.
% E.modo = 'AH' | 'HO' | 'AL' | 'otro' y E.modo_nombre; los ensayos salen ordenados por modo y luego por fecha.
% E.etiqueta = nombre legible para leyendas y títulos ('30/10 11:00 · AH'; año y robots solo si no son iguales en todos).
% leyenda(ax) reconoce los ensayos por el Tag de cada curva (= código), así que las curvas llevan 'Tag', E(i).codigo.
% Video time base: the time-lapse records exactly 2.997 frames per real second (30000/1001/10); VidFetch exported
% t, v and omega with the value set in its window (3.0 for these files, read from VP_..._info.json), so t is
% multiplied and v, omega divided by 3.0/2.997 (0.1 %: 3.6 s of drift against the sensor at minute 60).
% The sensor log is processed like FSRScope: uniform grid, G = ADC * K with K from the R of calibracion.csv,
% crop / exclusions / sync offset from datos/presion/config/<code>.json.
    raiz = fileparts(fileparts(fileparts(mfilename('fullpath'))));    % software/matlab_figuras/ -> repository
    if ischar(ensayos) && strcmp(ensayos, 'R_feedback')
        E = tabla_r_feedback(raiz);
        return
    end
    if ischar(ensayos) && strcmp(ensayos, 'exportar')
        E = @exportar;
        return
    end
    if ischar(ensayos) && strcmp(ensayos, 'estilos')
        E = @estilos;
        return
    end
    if ischar(ensayos) && strcmp(ensayos, 'leyenda')
        E = @leyenda_por_modo;
        return
    end
    if nargin < 2, duracion_s = Inf; end
    f = dir(fullfile(raiz, 'datos', 'video', 'trayectorias', 'VP_*_robots.csv'));
    todos = unique(regexprep({f.name}, '^VP_(.+?)(\(\d+\))?_robots\.csv$', '$1'));
    if isempty(ensayos)
        [sel, ok] = listdlg('ListString', todos, 'SelectionMode', 'multiple', ...
                            'PromptString', 'Ensayos:', 'ListSize', [300 300]);
        if ~ok, error('No se eligió ningún ensayo.'); end
        codigos = todos(sel);
    else
        codigos = todos(contains(todos, ensayos));
    end
    if isempty(codigos), error('Ningún ensayo coincide. Disponibles:\n  %s', strjoin(todos, '\n  ')); end
    % Order: by motion mode (AH, HO, AL, unknown), chronological inside each mode (sort is stable)
    codigos = sort(codigos);
    [~, o] = sort(cellfun(@(c) find([strcmp(modo_de(c), {'AH', 'HO', 'AL'}), true], 1), codigos));
    codigos = codigos(o);
    for i = 1:numel(codigos)
        fprintf('Leyendo %s\n', codigos{i});
        E(i) = leer_ensayo(raiz, codigos{i}, duracion_s); %#ok<AGROW>
    end
    et = etiquetas(codigos);
    [E.etiqueta] = et{:};
end

function e = leer_ensayo(raiz, codigo, duracion_s)
    % --- trajectories (one file, or parts (1), (2)... of a split video joined with the gap of cortes.json)
    carpeta = fullfile(raiz, 'datos', 'video', 'trayectorias');
    partes = dir(fullfile(carpeta, ['VP_' codigo '*_robots.csv']));
    T = table();
    for k = 1:numel(partes)
        Tk = leer_trayectoria(fullfile(carpeta, partes(k).name));
        if k > 1
            hueco = hueco_corte(raiz, codigo, k - 1);
            Tk.t_s = Tk.t_s + max(T.t_s) + hueco;
            Tk.frame = Tk.frame + max(T.frame) + 1 + round(hueco * fr_real());
        end
        T = [T; Tk]; %#ok<AGROW>
    end
    T = T(T.t_s >= 0 & T.t_s <= duracion_s, :);                       % video t = 0 is the end of the LED
    S = groupsummary(T, 'frame', 'mean', {'t_s', 'speed_mm_s'});      % one row per frame, NaN left out
    observado = ismember(T.status, ["detectado", "detectado (umbral relajado)", "manual"]);

    % --- sensor
    [ts, G, paso, desfase, K, R_lista, R_firmware] = leer_sensor(raiz, codigo, duracion_s);
    if isempty(ts)
        fprintf('  video %.1f min desde el fin del LED (sin registro del sensor)\n', max(T.t_s) / 60);
    else
        fprintf('  video %.1f min y sensor %.1f min desde el fin del LED (t_sensor = %.2f s)\n', ...
                max(T.t_s) / 60, (ts(end) - desfase) / 60, desfase);
    end
    G_cuadro = nan(height(S), 1);
    if ~isempty(G)
        idx = round((desfase + S.mean_t_s - ts(1)) / paso) + 1;        % nearest grid sample to every frame
        ok = idx >= 1 & idx <= numel(G);
        G_cuadro(ok) = G(idx(ok));
    end

    [modo, modo_nombre] = modo_de(codigo);
    e = struct('codigo', codigo, 'modo', modo, 'modo_nombre', modo_nombre, ...
               'raiz', raiz, 't', S.mean_t_s, 'V', S.mean_speed_mm_s, 'nf', height(S), ...
               'omega', T.omega(observado & isfinite(T.omega)), 'x', T.x_mm, 'y', T.y_mm, ...
               'ts', ts, 'G', G, 'G_cuadro', G_cuadro, 'paso', paso, 'desfase', desfase, 'K', K, ...
               'R_lista', R_lista, 'R_firmware', R_firmware);
end

function T = leer_trayectoria(archivo)
    o = detectImportOptions(archivo);
    o.SelectedVariableNames = intersect({'frame', 't_s', 'x_mm', 'y_mm', 'speed_mm_s', 'omega_deg_s', ...
                                         'omega_rad_s', 'status'}, o.VariableNames);
    o = setvartype(o, 'status', 'string');
    T = readtable(archivo, o);
    if ismember('omega_deg_s', T.Properties.VariableNames)
        T.omega = T.omega_deg_s;
    else
        T.omega = rad2deg(T.omega_rad_s);
    end
    T = T(:, {'frame', 't_s', 'x_mm', 'y_mm', 'speed_mm_s', 'omega', 'status'});

    % Real time base: t * f, v / f, omega / f with f = exported frames per second / 2.997
    f = fr_exportado(archivo) / fr_real();
    if abs(f - 1) > 1e-6
        T.t_s = T.t_s * f;  T.speed_mm_s = T.speed_mm_s / f;  T.omega = T.omega / f;
        [~, nombre] = fileparts(archivo);
        fprintf('  %s: base de tiempo %g -> %.4f cuadros/s reales (t x%.5f, v y ω /%.5f)\n', ...
                nombre, f * fr_real(), fr_real(), f, f);
    end
end

function fr = fr_real()
    % Frames per real second of the camera time-lapse (29.97 fps played, x10)
    fr = 30000 / 1001 / 10;
end

function fr = fr_exportado(archivo)
    % Frames per real second VidFetch used when it exported ARCHIVO (VP_..._info.json, 'cuadros_por_segundo_real')
    fr = 3.0;
    info = regexprep(archivo, '\.csv$', '_info.json');
    if isfile(info)
        J = jsondecode(fileread(info));
        if isfield(J, 'cuadros_por_segundo_real'), fr = J.cuadros_por_segundo_real; return; end
    end
    warning('%s: sin cuadros_por_segundo_real en el _info.json; se supone 3.0 cuadros/s.', archivo);
end

function hueco = hueco_corte(raiz, codigo, k)
    % Unrecorded seconds between part k and k+1 (datos/video/cortes.json, written by FSRScope / medir_corte.py)
    J = jsondecode(fileread(fullfile(raiz, 'datos', 'video', 'cortes.json')));
    hueco = J.(matlab.lang.makeValidName(codigo)).hueco_s(k);
end

function [tu, G, paso, desfase, K, R_lista, R_firmware] = leer_sensor(raiz, codigo, duracion_s)
    % G on a uniform grid, only from the end of the LED (desfase) to desfase + DURACION_S [s];
    % NaN inside that span where FSRScope excludes data
    tu = [];  G = [];  paso = NaN;  desfase = NaN;  K = NaN;  R_lista = NaN;  R_firmware = NaN;
    f = fullfile(raiz, 'datos', 'presion', 'crudos', ['R_' codigo '.csv']);
    if ~isfile(f), return; end
    [t, adc, lleno, led_fin, R_firmware] = leer_log(f, codigo, raiz);
    J = config(raiz, codigo);
    cal = ajustes(J, 'calibration', struct('v_ref', 3.3, 'v_exc', 0.7534, 'adc_fs', 1023));
    an = ajustes(J, 'analysis', struct('step_s', 0.05, 't_start', [], 't_end', [], 'exclusions', [], 'exclude_saturated', false));

    % --- K only from the R_FEEDBACK of calibracion.csv (nothing is computed from the log)
    R_lista = r_feedback_lista(raiz, codigo);
    if isnan(R_lista)
        error('%s no tiene R_FEEDBACK en datos/presion/calibracion.csv: agregá la fila "%s,<ohm>,<nota>".', codigo, codigo);
    end
    K = cal.v_ref * 1e6 / (cal.adc_fs * cal.v_exc * R_lista);

    desfase = led_fin;                                                 % t_sensor = desfase + t_video
    if isfield(J, 'sync') && isfield(J.sync, 'offset_auto') && ~J.sync.offset_auto, desfase = J.sync.offset_s; end
    if isnan(desfase), desfase = 0; end

    % --- uniform grid (same samples as FSRScope: it starts at t(1)), kept only from the LED end on
    paso = an.step_s;
    tu = (t(1):paso:t(end))';
    G = interp1(t, adc, tu) * K;
    dentro = tu >= desfase & tu <= desfase + duracion_s;
    tu = tu(dentro);  G = G(dentro);
    % --- analysis mask (crop, excluded spans, saturation if FSRScope says so)
    m = true(size(tu));
    if ~isempty(an.t_start), m = m & tu >= an.t_start; end
    if ~isempty(an.t_end), m = m & tu <= an.t_end; end
    ex = reshape(an.exclusions, [], 2);
    for j = 1:size(ex, 1)
        m = m & ~(tu >= min(ex(j, :)) & tu <= max(ex(j, :)));
    end
    if an.exclude_saturated
        m = m & ~(interp1(t, double(adc >= cal.adc_fs - 0.5 | lleno), tu, 'next', 1) > 0);
    end
    G(~m) = NaN;
end

function [t, adc, lleno, led_fin, R_firmware] = leer_log(f, codigo, raiz)
    % Valid rows of a sensor log: time [s] from the first valid row, ADC, full-scale flag, end of the LED pulse,
    % and the R_FEEDBACK the firmware used (from its G/ADC factor, with V_EXC of the FSRScope settings)
    T = readtable(f, 'VariableNamingRule', 'preserve');                % keeps 'timestamp(ms)' (no warning)
    T.Properties.VariableNames = lower(T.Properties.VariableNames);
    t = columna(T, {'timestamp(ms)'});
    adc = columna(T, {'adc_raw', 'adc'});
    G_fw = columna(T, {'g', 'g_us'});
    R_fw = columna(T, {'r', 'r_ohm'});
    led = columna(T, {'led'});
    lleno = columna(T, {'clipsat'}) >= columna(T, {'n'}) & columna(T, {'n'}) > 0;   % every oversampled reading clipped
    marca = false(height(T), 1);
    if ismember('sync', T.Properties.VariableNames), marca = ~ismissing(T.sync); end

    dts = diff(t(isfinite(t)));
    if median(dts(dts > 0)) > 5, t = t / 1000; end                      % milliseconds -> s
    t(abs(t - movmedian(t, 25, 'omitnan')) > 5) = NaN;                 % rows with an absurd time
    t = t - t(find(isfinite(t), 1));                                   % t0 = first valid row (same as the LED)
    on = find(led == 1);  led_fin = NaN;                               % end of the LAST LED pulse (video t = 0)
    if numel(on) >= 3
        pulsos = 1 + nnz(diff(on) > 1);
        if pulsos > 1
            warning('%s: %d pulsos de LED; se usa el fin del último (%.2f s).', codigo, pulsos, t(on(end)));
        end
        led_fin = t(on(end));
    end
    fila = isfinite(t) & isfinite(adc) & ~marca;
    [t, iu] = unique(t(fila));
    sel = find(fila);  sel = sel(iu);
    adc = adc(sel);  G_fw = G_fw(sel);  R_fw = R_fw(sel);  lleno = lleno(sel);

    K_fw = NaN;                                                        % firmware factor [uS/count]
    ok = adc > 0.05 & G_fw > 0;
    if nnz(ok) > 10
        K_fw = median(G_fw(ok) ./ adc(ok));
    else
        ok = adc > 0.05 & R_fw > 0;
        if nnz(ok) > 10, K_fw = median(1e6 ./ (R_fw(ok) .* adc(ok))); end
    end
    cal = ajustes(config(raiz, codigo), 'calibration', struct('v_ref', 3.3, 'v_exc', 0.7534, 'adc_fs', 1023));
    R_firmware = cal.v_ref * 1e6 / (cal.adc_fs * cal.v_exc * K_fw);
end

function R = tabla_r_feedback(raiz)
    % R_FEEDBACK of calibracion.csv vs the one the firmware used, for every sensor log
    f = dir(fullfile(raiz, 'datos', 'presion', 'crudos', 'R_*.csv'));
    codigo = regexprep({f.name}', '^R_|\.csv$', '');
    R_lista = nan(numel(f), 1);  R_firmware = R_lista;
    for i = 1:numel(f)
        R_lista(i) = r_feedback_lista(raiz, codigo{i});
        [~, ~, ~, ~, R_firmware(i)] = leer_log(fullfile(f(i).folder, f(i).name), codigo{i}, raiz);
    end
    G_por = R_firmware ./ R_lista;                                     % G with the list / G logged by the firmware
    coincide = abs(R_lista ./ R_firmware - 1) < 0.02;
    R = sortrows(table(string(codigo), R_lista, round(R_firmware), G_por, coincide, ...
        'VariableNames', {'codigo', 'R_lista_ohm', 'R_firmware_ohm', 'G_lista_sobre_G_firmware', 'coincide'}), 'codigo');
end

function J = config(raiz, codigo)
    J = struct();
    cfg = fullfile(raiz, 'datos', 'presion', 'config', [codigo '.json']);
    if isfile(cfg), J = jsondecode(fileread(cfg)); end
end

function x = columna(T, nombres)
    % First existing column of NOMBRES as double (NaN if none)
    x = nan(height(T), 1);
    for k = 1:numel(nombres)
        if ismember(nombres{k}, T.Properties.VariableNames)
            x = T.(nombres{k});
            if ~isnumeric(x), x = str2double(string(x)); end
            x = double(x);
            return
        end
    end
end

function s = ajustes(J, campo, s)
    % Defaults S overwritten by the fields present in J.(campo)
    if ~isfield(J, campo), return; end
    for f = fieldnames(s)'
        if isfield(J.(campo), f{1}), s.(f{1}) = J.(campo).(f{1}); end
    end
end

function r = r_feedback_lista(raiz, codigo)
    % R_FEEDBACK [ohm] from datos/presion/calibracion.csv (codigo,r_feedback_ohm,nota): the longest code prefix
    % wins; empty value -> NaN (then the FSRScope setting or the firmware factor is used)
    r = NaN;
    f = fullfile(raiz, 'datos', 'presion', 'calibracion.csv');
    if ~isfile(f), return; end
    o = detectImportOptions(f);
    o = setvartype(o, 'codigo', 'string');
    C = readtable(f, o);
    c = strtrim(C.codigo);
    k = find(strlength(c) > 0 & arrayfun(@(p) startsWith(codigo, p), c));
    if isempty(k), return; end
    [~, j] = max(strlength(c(k)));
    r = C.r_feedback_ohm(k(j));
    if ~(r > 0), r = NaN; end
end

function [clave, nombre] = modo_de(texto)
    % Motion mode from a code <date>_<time>_<robots><MODE>_<minutes> (also found inside a legend text).
    % AH = all counterclockwise (left motor), HO = all clockwise (right motor), AL = random;
    % old names: QR/QL -> AH, R -> AL. clave = '' if TEXTO holds no trial code (e.g. 'normal').
    clave = '';  nombre = '';
    texto = char(texto);
    if isempty(regexp(texto, '\d{8}_\d{4}', 'once')), return; end
    m = regexp(texto, '\d{8}_\d{4}_\d+([A-Za-z]+)_', 'tokens', 'once');
    if isempty(m), m = ''; else, m = upper(m{1}); end
    switch m
        case {'AH', 'QR', 'QL'}, clave = 'AH';   nombre = 'Antihorario';
        case 'HO',               clave = 'HO';   nombre = 'Horario';
        case {'AL', 'R'},        clave = 'AL';   nombre = 'Aleatorio';
        otherwise,               clave = 'otro'; nombre = 'Sin modo';
    end
end

function [colores, lineas, marcas] = estilos(E, linea_por_modo)
    % One colour per trial from the family of its mode (dark -> light in the order of E), plus line style
    % and marker per mode so the modes stay apart in grey-scale prints too
    if nargin < 2, linea_por_modo = true; end
    claves = {'AH', 'HO', 'AL', 'otro'};
    paleta = {[0.03 0.19 0.42; 0.13 0.44 0.71; 0.42 0.68 0.84], ...   % AH: blues
              [0.00 0.33 0.17; 0.17 0.58 0.27; 0.45 0.77 0.46], ...   % HO: greens
              [0.50 0.08 0.02; 0.85 0.28 0.00; 0.99 0.60 0.20], ...   % AL: reds / oranges
              [0.15 0.15 0.15; 0.40 0.40 0.40; 0.65 0.65 0.65]};      % unknown mode: greys
    trazo = {'-', '-.', '--', ':'};  marca = {'o', '^', 's', 'd'};
    n = numel(E);  colores = zeros(n, 3);  lineas = repmat({'-'}, 1, n);  marcas = repmat({'o'}, 1, n);
    for m = 1:numel(claves)
        k = find(strcmp({E.modo}, claves{m}));
        if isempty(k), continue; end
        if isscalar(k), s = 0.5; else, s = linspace(0, 1, numel(k)); end
        colores(k, :) = interp1([0 0.5 1], paleta{m}, s(:));
        if linea_por_modo, lineas(k) = trazo(m); end
        marcas(k) = marca(m);
    end
end

function et = etiquetas(codigos)
    % Readable names from codes AAAAMMDD_HHMM_NNMODO_TT: 'dd/mm HH:MM · MODO'. The year is added only if the
    % trials span several years and the number of robots only if it is not the same in all of them.
    tok = regexp(codigos, '^(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})_(\d+)', 'tokens', 'once');
    ok = find(~cellfun(@isempty, tok));
    con_anio = numel(unique(cellfun(@(t) t{1}, tok(ok), 'UniformOutput', false))) > 1;
    con_robots = numel(unique(cellfun(@(t) t{6}, tok(ok), 'UniformOutput', false))) > 1;
    et = codigos;                                      % codes that do not follow the pattern stay as they are
    for k = ok(:)'
        t = tok{k};
        txt = [t{3} '/' t{2}];
        if con_anio, txt = [txt '/' t{1}]; end %#ok<AGROW>
        txt = [txt ' ' t{4} ':' t{5}]; %#ok<AGROW>
        clave = modo_de(codigos{k});
        if ~strcmp(clave, 'otro'), txt = [txt ' · ' clave]; end %#ok<AGROW>
        if con_robots, txt = sprintf('%s · %s robots', txt, t{6}); end
        et{k} = txt;
    end
end

function leyenda_por_modo(ax)
    % Legend grouped by mode: a header entry (no symbol) before the trials of each mode, in drawing order.
    % Entries that are not a trial (e.g. the normal curve) go last. Without mixed modes it is a plain legend.
    if nargin < 1, ax = gca; end
    delete(findobj(ax, 'Tag', 'cabecera_modo'));
    h = flipud(ax.Children);                                           % Children = newest first
    h = h(arrayfun(@(o) isprop(o, 'DisplayName') && strlength(o.DisplayName) > 0, h));
    % trial code from the Tag (legend text is the readable name); DisplayName kept as fallback
    [clave, nombre] = arrayfun(@(o) modo_de([char(o.Tag) ' ' char(o.DisplayName)]), h, 'UniformOutput', false);
    ensayo = ~cellfun(@isempty, clave);
    if numel(unique(clave(ensayo))) < 2
        legend(ax, h);
        return
    end
    hold(ax, 'on');
    items = gobjects(0, 1);  previo = '';
    for k = find(ensayo)'
        if ~strcmp(clave{k}, previo)
            if strcmp(clave{k}, 'otro'), txt = upper(nombre{k}); else, txt = sprintf('%s (%s)', upper(nombre{k}), clave{k}); end
            items(end + 1, 1) = plot(ax, NaN, NaN, 'LineStyle', 'none', 'Marker', 'none', ...
                                     'Tag', 'cabecera_modo', 'DisplayName', txt); %#ok<AGROW>
            previo = clave{k};
        end
        items(end + 1, 1) = h(k); %#ok<AGROW>
    end
    legend(ax, [items; h(~ensayo)]);
end

function exportar(fig, base, formatos, dpi)
    % Save FIG as BASE.<ext> for every extension in FORMATOS (with or without the dot):
    %   .png .jpg .tif -> image at DPI;  .pdf .eps .emf -> vector (exportgraphics);  .svg -> vector (print);
    %   .fig -> MATLAB figure (savefig). White background whatever the MATLAB theme.
    if ischar(formatos) || isstring(formatos), formatos = cellstr(formatos); end
    for k = 1:numel(formatos)
        ext = lower(char(formatos{k}));
        if ext(1) ~= '.', ext = ['.' ext]; end
        archivo = [base ext];
        switch ext
            case {'.png', '.jpg', '.jpeg', '.tif', '.tiff'}
                exportgraphics(fig, archivo, 'Resolution', dpi, 'BackgroundColor', 'white');
            case {'.pdf', '.eps', '.emf'}
                exportgraphics(fig, archivo, 'ContentType', 'vector', 'BackgroundColor', 'white');
            case '.svg'
                print(fig, archivo, '-dsvg');
            case '.fig'
                savefig(fig, archivo);
            otherwise
                warning('Formato "%s" no soportado: usar .png .jpg .tif .pdf .eps .emf .svg o .fig', ext);
                continue
        end
        fprintf('  guardada %s\n', archivo);
    end
end