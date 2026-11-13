function E = cargar_datos(ensayos, duracion_s)
% CARGAR_DATOS  Lee los ensayos cuyo código contiene alguno de los textos de ENSAYOS ({} = elegir de una lista),
% solo los primeros DURACION_S segundos desde el inicio del video (Inf = todo). Una fila de E por ensayo:
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
% (datos/presion/crudos y datos/presion/Viejos).
% exportar = cargar_datos('exportar') devuelve una función para guardar figuras: exportar(fig, base, formatos, dpi),
% con formatos = {'.png', '.pdf', ...} (ver la función exportar al final).
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
    for i = 1:numel(codigos)
        fprintf('Leyendo %s\n', codigos{i});
        E(i) = leer_ensayo(raiz, codigos{i}, duracion_s); %#ok<AGROW>
    end
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
    inicio = min(T.t_s);
    T = T(T.t_s - inicio <= duracion_s, :);                           % only the first duracion_s of video
    S = groupsummary(T, 'frame', 'mean', {'t_s', 'speed_mm_s'});      % one row per frame, NaN left out
    observado = ismember(T.status, ["detectado", "detectado (umbral relajado)", "manual"]);

    % --- sensor
    [ts, G, paso, desfase, K, R_lista, R_firmware] = leer_sensor(raiz, codigo, [inicio, inicio + duracion_s]);
    G_cuadro = nan(height(S), 1);
    if ~isempty(G)
        idx = round((desfase + S.mean_t_s - ts(1)) / paso) + 1;        % nearest grid sample to every frame
        ok = idx >= 1 & idx <= numel(G);
        G_cuadro(ok) = G(idx(ok));
    end

    e = struct('codigo', codigo, 'raiz', raiz, 't', S.mean_t_s, 'V', S.mean_speed_mm_s, 'nf', height(S), ...
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

function [tu, G, paso, desfase, K, R_lista, R_firmware] = leer_sensor(raiz, codigo, ventana_video)
    % G on a uniform grid, NaN outside the analysed spans and outside VENTANA_VIDEO [s of video]
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

    % --- uniform grid and analysis mask (crop, excluded spans, saturation if FSRScope says so, video window)
    paso = an.step_s;
    tu = (t(1):paso:t(end))';
    G = interp1(t, adc, tu) * K;
    m = tu - desfase >= ventana_video(1) & tu - desfase <= ventana_video(2);
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
    on = find(led == 1);  led_fin = NaN;
    if numel(on) >= 3
        corte = find(diff(on) > 1, 1);
        if ~isempty(corte), on = on(1:corte); end
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
    f = [dir(fullfile(raiz, 'datos', 'presion', 'crudos', 'R_*.csv')); dir(fullfile(raiz, 'datos', 'presion', 'Viejos', 'R_*.csv'))];
    codigo = regexprep({f.name}', '^R_|\.csv$', '');
    carpeta = regexprep({f.folder}', '.*[\\/]', '');              % last folder name: crudos | Viejos
    R_lista = nan(numel(f), 1);  R_firmware = R_lista;
    for i = 1:numel(f)
        R_lista(i) = r_feedback_lista(raiz, codigo{i});
        [~, ~, ~, ~, R_firmware(i)] = leer_log(fullfile(f(i).folder, f(i).name), codigo{i}, raiz);
    end
    G_por = R_firmware ./ R_lista;                                     % G with the list / G logged by the firmware
    coincide = abs(R_lista ./ R_firmware - 1) < 0.02;
    R = sortrows(table(string(codigo), string(carpeta), R_lista, round(R_firmware), G_por, coincide, ...
        'VariableNames', {'codigo', 'carpeta', 'R_lista_ohm', 'R_firmware_ohm', 'G_lista_sobre_G_firmware', 'coincide'}), 'codigo');
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
