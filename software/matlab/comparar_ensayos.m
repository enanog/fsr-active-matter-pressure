%% comparar_ensayos.m
% Overlay of several trials (VP_<code>_robots.csv exported by VidFetch): V_mean(t), <|omega|>(t),
% kinetic energy, histogram, PDF, 1 - F(v), and speed vs pressure (G of the FSR sensor), one
% window per plot, plus a summary table.
%
% - Files: list them in `archivos` or leave it empty to pick them in a dialog (multi-select).
% - Split recordings: picking VP_<code>(1)_robots.csv and VP_<code>(2)_robots.csv joins them into
%   one trial with the gap stored in datos/video/cortes.json.
% - Pressure: read from datos/presion/crudos/R_<code>.csv like FSRScope does (time from the first
%   valid row; G from the firmware factor, or ADC*K of the circuit parameters if the FSRScope
%   calibration of the trial is manual; sync = end of the LED pulse unless FSRScope has a manual
%   offset; FSRScope crop and excluded spans honoured). A warning is printed when the manual K
%   differs from the firmware one by more than 2 %.
% - Show / hide traces: click an entry of any legend (all the curves of that trial in the figure
%   toggle together). `ocultar` lists trials hidden from the start.
% - Time plots show only the moving average; distributions use the raw (unsmoothed) data.

clear; clc;

%% ===================== Parameters =====================
carpeta  = "C:\Users\dylan\Desktop\Proyecto_PresionRecintoCircular\datos\video\trayectorias";
archivos = strings(0);   % e.g. [fullfile(carpeta,"VP_20261030_1200_22AL_60_robots.csv"), ...]; empty -> dialog
ocultar  = strings(0);   % trials hidden at start, by (part of) the code, e.g. ["20261030_1200", "2509_1500"]

suav_s         = 30;     % moving average of the time plots and of the speed-pressure comparison [s]
usar_media     = true;   % distributions of: true = V_mean per frame, false = individual |v|
dist_suavizada = false;  % true: distributions of the smoothed V_mean (changes width and tails!)
n_clases       = 60;     % histogram / PDF bins (common to all trials)
normalizar_ccdf = true;  % figure 7: X axis v/<v> (dimensionless, <v> = mean of each trial's samples)

umbral        = 0.35;    % jam threshold on the smoothed V_mean [mm/s] (same default as velocidades.py)
suav_atasco_s = 30;      % moving median for the jam criterion [s]
min_atasco_s  = 20;      % minimum jam duration [s]

n_clases_vg = 25;        % V_mean bins for the G vs V_mean plot
min_cuadros = 30;        % a bin needs at least this many frames (10 s) to be drawn
mostrar_nube = false;    % G vs V_mean: also draw every frame as a point cloud
G_piso = 1e-3;           % G below this [uS] is resampling round-off: hidden on log axes

m_g  = NaN;              % robot mass [g]; NaN -> energy per unit mass
k_I  = 0.5;              % I = k_I * m * R^2 (0.5 = uniform disk; assumption)
R_mm = 33/2;             % robot radius [mm]

guardar_figuras = false; % true: export every figure as vector PDF
carpeta_figuras = "C:\Users\dylan\Desktop\Proyecto_PresionRecintoCircular\informes\comparacion_matlab";

%% ===================== Choose files =====================
if isempty(archivos)
    [nom, ruta] = uigetfile(fullfile(carpeta, "*_robots.csv"), ...
                            "Elegí uno o más VP_..._robots.csv", "MultiSelect", "on");
    if isequal(nom, 0)
        error("No se eligió ningún archivo.");
    end
    archivos = string(fullfile(ruta, string(nom)));
end
archivos = archivos(:);

% Group parts of split recordings by trial code
codigos = strings(size(archivos));
partes  = ones(size(archivos));
for i = 1:numel(archivos)
    [~, base] = fileparts(archivos(i));
    base = char(base);                                   % char: an unmatched group gives ''
    tok = regexp(base, '^VP_(.+?)(?:\((\d+)\))?_robots$', 'tokens', 'once');
    if isempty(tok)
        error("Nombre inesperado: %s (se espera VP_<código>_robots.csv)", base);
    end
    codigos(i) = string(tok{1});
    if numel(tok) > 1 && ~isempty(tok{2})
        partes(i) = str2double(tok{2});
    end
end
[cod_unicos, ~, idx_cod] = unique(codigos, "stable");

%% ===================== Load and process every trial =====================
if isnan(m_g)
    escala = 1;    unidad_E = 'E / m [\muJ/kg]';
else
    escala = m_g;  unidad_E = 'E [nJ]';            % 1 g * 1 uJ/kg = 1 nJ
end
avg = @(x) mean(x, 'omitnan');
D = struct([]);

for c = 1:numel(cod_unicos)
    sel = find(idx_cod == c);
    [~, orden] = sort(partes(sel));
    sel = sel(orden);
    T = table();
    t_fin = NaN;  frame_fin = -1;
    for j = 1:numel(sel)
        f = archivos(sel(j));
        fprintf("Leyendo %s ...\n", f);
        opts = detectImportOptions(f);
        opts.SelectedVariableNames = intersect({'frame','t_s','particle','speed_mm_s','omega_rad_s'}, ...
                                               opts.VariableNames, 'stable');
        Tj = readtable(f, opts);
        if j > 1                                         % next part of a split recording
            hueco = hueco_corte(f, cod_unicos(c), j - 1);
            Tj.t_s   = Tj.t_s + t_fin + hueco;           % same rule as comparar_modos.py
            Tj.frame = Tj.frame + frame_fin + 1 + round(hueco * 3);
            fprintf("  parte %d unida con un hueco de %.2f s\n", partes(sel(j)), hueco);
        end
        t_fin = max(Tj.t_s);  frame_fin = max(Tj.frame);
        if isempty(T), T = Tj; else, T = [T; Tj]; end %#ok<AGROW>
    end

    N = numel(unique(T.particle));
    [g, ~] = findgroups(T.frame);
    t  = splitapply(avg, T.t_s, g);                      % video time [s]
    v  = splitapply(avg, T.speed_mm_s, g);               % V_mean [mm/s]
    e_tr = N * splitapply(avg, 0.5 * T.speed_mm_s.^2, g);
    if ismember('omega_rad_s', T.Properties.VariableNames)
        w     = rad2deg(splitapply(avg, abs(T.omega_rad_s), g));                  % <|omega|> [deg/s]
        e_rot = N * splitapply(avg, 0.5 * k_I * R_mm^2 * T.omega_rad_s.^2, g);
    else
        w = nan(size(t));  e_rot = nan(size(t));
    end
    [t, orden] = sort(t);
    v = v(orden);  w = w(orden);  e_tr = escala * e_tr(orden);  e_rot = escala * e_rot(orden);

    mm = @(x) movmean(x, suav_s, 'omitnan', 'SamplePoints', t);
    if usar_media
        muestras = v;
        if dist_suavizada, muestras = mm(v); end
    else
        muestras = T.speed_mm_s;
    end
    muestras = muestras(isfinite(muestras));

    [frac, n_at, dmax, mascara, tramos] = atascos(t, v, umbral, suav_atasco_s, min_atasco_s);

    % --- pressure of the same trial, on the video frames ------------------------------------
    P = leer_presion(fileparts(archivos(sel(1))), cod_unicos(c));
    G_s = nan(size(t));  G_fr = nan(size(t));
    if ~isempty(P)
        ts = P.offset + t;                                       % sensor time of every frame
        G_s  = interp1(P.t, movmean(P.G, suav_s, 'omitnan', 'SamplePoints', P.t), ts, 'linear', NaN);
        G_fr = interp1(P.t, P.G, ts, 'nearest', NaN);            % raw G at each frame
        fprintf("  presión: %s, desfase video-sensor %.2f s (%s)\n", P.archivo, P.offset, P.origen_desfase);
    else
        fprintf("  sin registro del sensor para %s\n", cod_unicos(c));
    end
    ok = isfinite(G_fr);
    rho = spearman(mm(v), G_s);

    D(c).codigo   = cod_unicos(c);
    D(c).etiqueta = etiqueta(cod_unicos(c));
    D(c).tag      = char(D(c).etiqueta);
    D(c).N        = N;
    D(c).t        = t;
    D(c).v_s      = mm(v);
    D(c).w_s      = mm(w);
    D(c).Etr_s    = mm(e_tr);
    D(c).Erot_s   = mm(e_rot);
    D(c).Etot_s   = mm(e_tr + e_rot);
    D(c).G_s      = G_s;
    D(c).tramos   = tramos;
    D(c).muestras = muestras;
    D(c).resumen  = [mean(v,'omitnan'), std(v,'omitnan'), median(muestras), mean(w,'omitnan'), ...
                     mean(e_tr,'omitnan'), mean(e_rot,'omitnan'), ...
                     mean(e_rot,'omitnan') / mean(e_tr,'omitnan'), 100 * frac, n_at, dmax, ...
                     mean(G_fr(ok),'omitnan'), mean(G_fr(ok & ~mascara),'omitnan'), ...
                     mean(G_fr(ok & mascara),'omitnan'), rho];
end

%% ===================== Summary table =====================
nombres = {'V_media_mm_s','V_desvio_temporal','mediana_dist_mm_s','omega_abs_deg_s', ...
           'E_tras','E_rot','E_rot_sobre_E_tras','atasco_pct','n_atascos','atasco_max_s', ...
           'G_media_uS','G_flujo_uS','G_atasco_uS','rho_Spearman_V_G'};
R = array2table(vertcat(D.resumen), 'VariableNames', nombres, 'RowNames', {D.tag});
fprintf("\nResumen (energía en %s; umbral %.2f mm/s sobre V_media con mediana móvil %g s, >= %g s;\n", ...
        strrep(unidad_E, '\mu', 'u'), umbral, suav_atasco_s, min_atasco_s);
fprintf("G durante el video; rho = correlación de Spearman entre V_media y G suavizadas %g s)\n", suav_s);
disp(R);

%% ===================== Common distribution bins =====================
if usar_media
    txt_dist = 'V_{media} por cuadro';
    if dist_suavizada, txt_dist = sprintf('V_{media} suavizada %g s (cambia ancho y colas)', suav_s); end
else
    txt_dist = '|v| individual';
end
v_max   = max(cellfun(@max, {D.muestras}));
edges   = linspace(0, v_max, n_clases + 1);
centros = 0.5 * (edges(1:end-1) + edges(2:end));

%% ===================== Figures: one window per plot =====================
C = lines(numel(D));
txt_mm = sprintf('media móvil %g s', suav_s);
leg = {D.tag};
figs = gobjects(0);

% --- 1. V_mean vs time ------------------------------------------------------------
figs(end+1) = nueva_fig('V media vs tiempo');
for c = 1:numel(D)
    [x, y] = romper_huecos(D(c).t, D(c).v_s);
    plot(x/60, y, 'LineWidth', 1.6, 'Color', C(c,:), 'Tag', D(c).tag); hold on;
end
yline(umbral, '--', sprintf('umbral %.2f mm/s', umbral), 'HandleVisibility', 'off');
hold off; grid on;
title(['V_{media} del conjunto (' txt_mm ')']);
xlabel('t video [min]'); ylabel('V_{media} [mm/s]'); leyenda(leg);

% --- 2. <|omega|> vs time ---------------------------------------------------------
figs(end+1) = nueva_fig('Rotacion media vs tiempo');
for c = 1:numel(D)
    [x, y] = romper_huecos(D(c).t, D(c).w_s);
    plot(x/60, y, 'LineWidth', 1.6, 'Color', C(c,:), 'Tag', D(c).tag); hold on;
end
hold off; grid on;
title(['<|\omega|> del conjunto (' txt_mm ')']);
xlabel('t video [min]'); ylabel('<|\omega|> [°/s]'); leyenda(leg);

% --- 3. Total kinetic energy --------------------------------------------------------
figs(end+1) = nueva_fig('Energia cinetica total');
for c = 1:numel(D)
    [x, y] = romper_huecos(D(c).t, D(c).Etot_s);
    plot(x/60, y, 'LineWidth', 1.6, 'Color', C(c,:), 'Tag', D(c).tag); hold on;
end
hold off; grid on;
title(sprintf('Energía cinética total del conjunto (%s, I = %.2g mR^2)', txt_mm, k_I));
xlabel('t video [min]'); ylabel(unidad_E); leyenda(leg);

% --- 4. Translation (solid) and rotation (dashed) -----------------------------------
figs(end+1) = nueva_fig('Energia traslacion y rotacion');
h = gobjects(numel(D), 1);
for c = 1:numel(D)
    [x, y] = romper_huecos(D(c).t, D(c).Etr_s);
    h(c) = plot(x/60, y, '-', 'LineWidth', 1.4, 'Color', C(c,:), 'Tag', D(c).tag); hold on;
    [x, y] = romper_huecos(D(c).t, D(c).Erot_s);
    plot(x/60, y, '--', 'LineWidth', 1.4, 'Color', C(c,:), 'Tag', D(c).tag, 'HandleVisibility', 'off');
end
hold off; grid on;
title(sprintf('Traslación \\Sigma½mv^2 (continua) y rotación \\Sigma½I\\omega^2 (punteada), %s', txt_mm));
xlabel('t video [min]'); ylabel(unidad_E); leyenda(leg, h);

% --- 5. Histogram (fraction, so different durations are comparable) -----------------
figs(end+1) = nueva_fig('Histograma de velocidades');
for c = 1:numel(D)
    histogram(D(c).muestras, edges, 'Normalization', 'probability', 'DisplayStyle', 'stairs', ...
              'LineWidth', 1.6, 'EdgeColor', C(c,:), 'Tag', D(c).tag); hold on;
end
hold off; grid on;
title(['Histograma: ' txt_dist]);
xlabel('v [mm/s]'); ylabel('fracción de las muestras'); leyenda(leg);

% --- 6. PDF ------------------------------------------------------------------------
% figs(end+1) = nueva_fig('Densidad de probabilidad P(v)');
for c = 1:numel(D)
    p = histcounts(D(c).muestras, edges, 'Normalization', 'pdf');
    p(p == 0) = NaN;                                   % log axis: skip empty bins
    semilogy(centros, p, 'o-', 'LineWidth', 1.4, 'MarkerSize', 3, 'Color', C(c,:), 'Tag', D(c).tag); hold on;
end
hold off; grid on;
title(['P(v): ' txt_dist]);
xlabel('v [mm/s]'); ylabel('P(v) [s/mm]'); leyenda(leg);

% --- 7. 1 - F(v) ---------------------------------------------------------------------
% Normalised: only the X axis changes (u = v/<v>); Y stays a probability, P(U >= u) = P(V >= v).
figs(end+1) = nueva_fig('1 - F(v)');
for c = 1:numel(D)
    x = sort(D(c).muestras);
    y = (numel(x):-1:1)' / numel(x);                   % P(V >= v), never 0
    if normalizar_ccdf
        x = x / mean(x);
    end
    loglog(x, y, 'LineWidth', 1.8, 'Color', C(c,:), 'Tag', D(c).tag); hold on;
end
if usar_media && ~dist_suavizada && ~normalizar_ccdf
    % In v/<v> units the threshold differs between trials (umbral/<v>), so it is drawn only in mm/s.
    xline(umbral, '--', sprintf('umbral %.2f', umbral), 'HandleVisibility', 'off');
end
hold off; grid on;
if normalizar_ccdf
    title(['1 - F(v/\langle v \rangle): ' txt_dist ' normalizada por la media de cada ensayo']);
    xlabel('v / \langle v \rangle'); ylabel('1 - F = P(V / \langle V \rangle \geq u)');
else
    title(['1 - F(v): ' txt_dist]);
    xlabel('v [mm/s]'); ylabel('1 - F(v) = P(V \geq v)');
end
leyenda(leg);

% --- 8. G vs V_mean (all trials) -------------------------------------------------------
con_G = find(arrayfun(@(d) any(isfinite(d.G_s)), D));
if ~isempty(con_G)
    figs(end+1) = nueva_fig('Presion vs velocidad');
    vmax_s = max(arrayfun(@(d) max(d.v_s), D(con_G)));
    ev = linspace(0, vmax_s, n_clases_vg + 1);
    cv = 0.5 * (ev(1:end-1) + ev(2:end));
    h = gobjects(numel(con_G), 1);
    for k = 1:numel(con_G)
        c = con_G(k);
        x = D(c).v_s;  y = D(c).G_s;
        okk = isfinite(x) & isfinite(y) & y >= G_piso;
        if mostrar_nube
            scatter(x(okk), y(okk), 4, C(c,:), 'filled', 'MarkerFaceAlpha', 0.08, ...
                    'Tag', D(c).tag, 'HandleVisibility', 'off'); hold on;
        end
        xo = x(okk);  yo = y(okk);
        bin = discretize(xo, ev);
        b = ~isnan(bin);
        med = accumarray(bin(b), yo(b), [n_clases_vg 1], @median, NaN);
        cnt = accumarray(bin(b), 1, [n_clases_vg 1]);
        med(cnt < min_cuadros) = NaN;
        h(k) = semilogy(cv, med, 'o-', 'LineWidth', 1.6, 'MarkerSize', 5, 'Color', C(c,:), ...
                        'MarkerFaceColor', C(c,:), 'Tag', D(c).tag); hold on;
    end
    set(gca, 'YScale', 'log');
    xline(umbral, '--', sprintf('umbral %.2f', umbral), 'HandleVisibility', 'off');
    hold off; grid on;
    title(sprintf('G mediana por clase de V_{media} (ambas suavizadas %g s; clases con >= %d cuadros)', ...
                  suav_s, min_cuadros));
    xlabel('V_{media} [mm/s]'); ylabel('G [\muS]');
    leyenda({D(con_G).tag}, h);
end

% --- 9. V_mean and G vs time, one window per trial (twin axes) ----------------------------
for c = con_G(:)'
    figs(end+1) = nueva_fig(['V media y presion - ' D(c).tag]); %#ok<SAGROW>
    yyaxis left
    [x, y] = romper_huecos(D(c).t, D(c).v_s);
    hv = plot(x/60, y, '-', 'LineWidth', 1.8, 'Color', [0.16 0.50 0.38]);
    ylabel('V_{media} [mm/s]');
    yl = [0, 1.05 * max(y, [], 'omitnan')];
    ylim(yl);
    hold on;
    for j = 1:size(D(c).tramos, 1)                        % jams shaded
        a = D(c).tramos(j, 1) / 60;  b = D(c).tramos(j, 2) / 60;
        patch([a b b a], [yl(1) yl(1) yl(2) yl(2)], [0.48 0.25 0.63], 'FaceAlpha', 0.15, ...
              'EdgeColor', 'none', 'HandleVisibility', 'off');
    end
    hold off;
    ax = gca;  ax.YColor = [0.16 0.50 0.38];
    yyaxis right
    yG = D(c).G_s;  yG(yG < G_piso) = NaN;
    [x, y] = romper_huecos(D(c).t, yG);
    hg = semilogy(x/60, y, '-', 'LineWidth', 1.2, 'Color', [0.12 0.37 0.66]);
    ylabel('G [\muS]');  ax.YColor = [0.12 0.37 0.66];  ax.YScale = 'log';
    grid on;
    title(sprintf('%s: V_{media} y G (%s; violeta = atasco, %.1f %% del tiempo; \\rho = %.2f)', ...
                  D(c).tag, txt_mm, D(c).resumen(8), D(c).resumen(14)));
    xlabel('t video [min]');
    leyenda({'V_{media} (izq.)', 'G (der.)'}, [hv; hg]);
end

%% ===================== Initially hidden trials =====================
for c = 1:numel(D)
    if ~isempty(ocultar) && any(contains(D(c).codigo, ocultar))
        set(findobj(figs, 'Tag', D(c).tag), 'Visible', 'off');
    end
end

%% ===================== Export =====================
if guardar_figuras
    if ~isfolder(carpeta_figuras), mkdir(carpeta_figuras); end
    for i = 1:numel(figs)
        nombre = matlab.lang.makeValidName(figs(i).Name);
        exportgraphics(figs(i), fullfile(carpeta_figuras, nombre + ".pdf"), 'ContentType', 'vector');
    end
    writetable(R, fullfile(carpeta_figuras, "resumen_matlab.csv"), 'WriteRowNames', true);
    fprintf("Figuras y resumen guardados en %s\n", carpeta_figuras);
end

%% ===================== Local functions =====================
function f = nueva_fig(nombre)
    f = figure('Name', nombre, 'NumberTitle', 'off', 'Position', [100 100 950 580]);
end

function lg = leyenda(textos, objetos)
    % Legend whose entries show / hide their curves on click
    if nargin > 1
        lg = legend(objetos, textos, 'Location', 'best');
    else
        lg = legend(textos, 'Location', 'best');
    end
    lg.Title.String = 'clic: mostrar / ocultar';
    lg.ItemHitFcn = @alternar_traza;
end

function alternar_traza(~, evt)
    % All the objects of the figure with the same Tag (one trial) toggle together
    obj = evt.Peer;
    if isprop(obj, 'Tag') && ~isempty(obj.Tag)
        objs = findobj(ancestor(obj, 'figure'), 'Tag', obj.Tag);
    else
        objs = obj;
    end
    if strcmp(obj.Visible, 'on'), nuevo = 'off'; else, nuevo = 'on'; end
    set(objs, 'Visible', nuevo);
end

function txt = etiqueta(codigo)
    % '20261030_1200_22AL_60' -> "30/10 12:00 · 22AL" (files store AAAADDMM; August logs AAAAMMDD)
    p = split(codigo, "_");
    d = char(p(1));  hm = char(p(2));
    a = str2double(d(5:6));  b = str2double(d(7:8));
    if a <= 12 && b > 12
        dia = b;  mes = a;
    else
        dia = a;  mes = b;
    end
    txt = string(sprintf('%02d/%02d %s:%s · %s', dia, mes, hm(1:2), hm(3:4), char(p(3))));
end

function hueco = hueco_corte(archivo, codigo, k)
    % Gap [s] between part k and k+1 of a split recording, from datos/video/cortes.json
    cortes = fullfile(fileparts(fileparts(archivo)), "cortes.json");
    if ~isfile(cortes)
        error("%s está partido pero no existe %s (correr medir_corte.py).", codigo, cortes);
    end
    J = jsondecode(fileread(cortes));
    campo = matlab.lang.makeValidName(char(codigo));
    if ~isfield(J, campo)
        error("%s no figura en cortes.json.", codigo);
    end
    hueco = J.(campo).hueco_s(k);
end

function [frac, n, dmax, mascara, tramos] = atascos(t, v, umbral, suav_s, min_s)
    % Jam = moving median of V_mean below the threshold for at least min_s (as in velocidades.py)
    s = movmedian(v, suav_s, 'omitnan', 'SamplePoints', t);
    abajo = s(:) < umbral;
    d = diff([false; abajo; false]);
    ini = find(d == 1);  fin = find(d == -1) - 1;
    dt = median(diff(t));
    dur = t(fin) - t(ini) + dt;
    ok = dur >= min_s;
    mascara = false(size(abajo));
    for j = find(ok)'
        mascara(ini(j):fin(j)) = true;
    end
    frac = mean(mascara);
    n = nnz(ok);
    dmax = max([dur(ok); 0]);
    tramos = [t(ini(ok)), t(fin(ok)) + dt];             % [start end] video time [s]
end

function rho = spearman(x, y)
    % Spearman rank correlation without the Statistics Toolbox (ties are negligible here)
    ok = isfinite(x) & isfinite(y);
    if nnz(ok) < 10, rho = NaN; return; end
    rx = zeros(nnz(ok), 1);  ry = rx;
    [~, ix] = sort(x(ok));  rx(ix) = 1:nnz(ok);
    [~, iy] = sort(y(ok));  ry(iy) = 1:nnz(ok);
    r = corrcoef(rx, ry);
    rho = r(1, 2);
end

function P = leer_presion(carpeta_traj, codigo)
    % Sensor log R_<code>.csv as FSRScope reads it; [] if there is none.
    raiz = fileparts(fileparts(fileparts(carpeta_traj)));        % .../datos/video/trayectorias -> repo
    f = fullfile(raiz, "datos", "presion", "crudos", "R_" + codigo + ".csv");
    P = [];
    if ~isfile(f), return; end
    opts = detectImportOptions(f, 'VariableNamingRule', 'preserve');
    opts = setvartype(opts, 'double');
    T = readtable(f, opts);
    nombres = lower(strtrim(string(T.Properties.VariableNames)));
    col = @(c) find(ismember(nombres, c), 1);

    it = col(["timestamp(ms)", "timestamp", "tiempo", "time", "t_s"]);
    if isempty(it), it = 1; end
    t = T{:, it};
    dts = diff(t(isfinite(t)));  dts = dts(dts > 0);
    if ~isempty(dts) && median(dts) > 5, t = t / 1000; end      % real milliseconds
    med = movmedian(t, 25, 'omitnan');
    t(abs(t - med) > 5) = NaN;                                    % junk rows (absurd time)
    t = t - t(find(isfinite(t), 1));                              % t0 = first valid row (as the LED)

    led_off = NaN;
    il = col("led");
    if ~isempty(il)
        on = find(T{:, il} == 1);
        if numel(on) >= 3
            br = find(diff(on) > 1, 1);
            if ~isempty(br), on = on(1:br); end
            led_off = t(on(end));
        end
    end

    ig = col(["g", "g_us"]);  ir = col(["r", "r_ohm"]);  ia = col(["adc_raw", "adc"]);
    if ~isempty(ig)
        G = T{:, ig};                                             % G logged by the firmware [uS]
    elseif ~isempty(ir)
        G = 1e6 ./ T{:, ir};
    else
        return
    end
    J = struct();
    cfg = fullfile(raiz, "datos", "presion", "config", codigo + ".json");
    if isfile(cfg), J = jsondecode(fileread(cfg)); end
    if isfield(J, 'calibration') && strcmp(J.calibration.mode, 'manual') && ~isempty(ia)
        cal = J.calibration;
        adc = T{:, ia};
        K = cal.v_ref * 1e6 / (cal.adc_fs * cal.v_exc * cal.r_feedback);   % [uS/count]
        okk = adc > 0.05 & G > 0 & isfinite(G);
        K_fw = median(G(okk) ./ adc(okk));
        if ~isnan(K_fw) && abs(K / K_fw - 1) > 0.02
            warning("%s: calibración manual de FSRScope (R_FEEDBACK = %g ohm, K = %.4g uS/cuenta) " + ...
                    "difiere del firmware (K = %.4g, R_FEEDBACK equivalente %.0f ohm): G x %.3g. Revisar.", ...
                    codigo, cal.r_feedback, K, K_fw, cal.r_feedback * K / K_fw, K / K_fw);
        end
        G = adc * K;                                              % same as FSRScope in manual mode
    end
    keep = isfinite(t) & isfinite(G);
    is = col("sync");
    if ~isempty(is), keep = keep & isnan(T{:, is}); end           % drop SYNC marker rows
    [t, iu] = unique(t(keep));
    G = G(keep);  G = G(iu);

    % FSRScope settings of the trial: manual offset, crop and excluded spans
    origen = "fin del LED";  offset = led_off;
    if ~isempty(fieldnames(J))
        if isfield(J, 'sync') && isfield(J.sync, 'offset_auto') && ~J.sync.offset_auto
            offset = J.sync.offset_s;  origen = "manual (FSRScope)";
        end
        if isfield(J, 'analysis')
            a = J.analysis;
            if isfield(a, 't_start') && ~isempty(a.t_start), G(t < a.t_start) = NaN; end
            if isfield(a, 't_end') && ~isempty(a.t_end),     G(t > a.t_end) = NaN; end
            if isfield(a, 'exclusions') && ~isempty(a.exclusions)
                ex = reshape(a.exclusions, [], 2);
                for j = 1:size(ex, 1)
                    G(t >= min(ex(j,:)) & t <= max(ex(j,:))) = NaN;
                end
            end
        end
    end
    if isnan(offset)
        offset = 0;  origen = "sin pulso LED: 0 s";
    end
    [~, nom, ext] = fileparts(f);
    P = struct('t', t, 'G', G, 'offset', offset, 'origen_desfase', origen, 'archivo', nom + ext);
end

function [x, y] = romper_huecos(t, y)
    % Insert a NaN where time jumps (gap of a split video) so the line is not drawn across it
    salto = find(diff(t) > 5 * median(diff(t)));
    x = t(:);  y = y(:);
    for j = flipud(salto(:))'
        x = [x(1:j); (x(j) + x(j+1)) / 2; x(j+1:end)];
        y = [y(1:j); NaN; y(j+1:end)];
    end
end
