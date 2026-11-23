%% figuras.m  -  comparación de ensayos: velocidad, energía, ocupación, G, V vs G y G en atasco vs libre
% Un solo archivo, en bloques: AJUSTES (todo lo que se cambia, agrupado por figura) -> DATOS -> VELOCIDAD Y ENERGÍA
% (figs. 1-5) -> G (figs. 6-13) -> ATASCO VS LIBRE (figs. 14-15). Cada sección %% es una figura: Ctrl+Enter corre
% solo esa sección, F5 corre todas. Cada figura dice en "Usa:" qué ajustes la cambian.
% Los datos salen de datos/video/trayectorias/VP_<código>_robots.csv y datos/presion/crudos/R_<código>.csv,
% procesados como FSRScope (ver cargar_datos.m). Cada ensayo tiene el mismo color en todas las figuras.
% Modo de movimiento (del código): AH antihorario = azules y trazo continuo, HO horario = verdes y trazo-punto,
% AL aleatorio = rojos/naranjas y trazo cortado. Los ensayos se ordenan por modo y luego por fecha.
% Requiere MATLAB R2020b+ y Statistics and Machine Learning Toolbox (skewness, corr, normpdf, prctile, ksdensity).

clc; clear; close all;

%% ========================================== AJUSTES ==========================================
% Todo lo que se cambia está acá, agrupado por las figuras que lo usan. Después de cambiar un valor: Ctrl+Enter en
% esta sección y después en la figura (o F5 para todo). Si cambiás algo de "General", "Energía" o "G", correr también
% DATOS (los ensayos solo se vuelven a leer si cambia "ensayos" o "duracion_min").

% ---- General (todas las figuras) ----
ensayos = {                         % part of the codes; {} = pick from a list
    '20261030_1100'
    '20261030_1200'
    '20261030_1430'
    '20261030_1600'
    '20261106_1600'
    '20261112_1600'
    '20261116_1100'
};
% ensayos = {};
duracion_min        = 60;           % minutes after the end of the LED (the video starts there; the sensor is cut to the same span); Inf = all
linea_por_modo      = true;         % true: line style per mode (AH -, HO -., AL --) besides the colour family; false: all solid

% ---- Guardar figuras (todas) ----
guardar             = false;        %#ok<*UNRCH> true: every figure -> informes/figuras/matlab_figuras/<figura>__<códigos>.<formato>
formatos = {                        % one per line; put % in front of a line to switch that format off (Ctrl+R / Ctrl+T)
    '.png'                          % image (uses "resolucion")
    % '.pdf'                        % vector
    % '.svg'                        % vector
    % '.eps'                        % vector
    % '.emf'                        % vector (Word / PowerPoint)
    % '.jpg'                        % image
    % '.tif'                        % image
    % '.fig'                        % MATLAB figure, can be opened and edited again
};
resolucion          = 300;          % dpi of the images (.png .jpg .tif)

% ---- Velocidad (figuras 1 y 6: curvas en el tiempo; 1, 13 y 14: umbral) ----
suav                = 10;           % moving average of the time plots [s]
umbral              = 0.35;         % jam threshold of V media [mm/s]: line of figures 1 and 13, manual threshold of 14-15

% ---- Energía cinética (figura 4c) ----
masa_g              = 0;            % mass of one robot [g]; 0 = kinetic energy per unit mass [mm^2/s^2 = uJ/kg]
diametro_mm         = 33;           % robot body diameter [mm] (R = diametro_mm / 2 in E_rot)
k_inercia           = 0.5;          % moment of inertia I = k m R^2 (0.5 = uniform disc)
energia_log         = false;        % figure 4b (commented) on a log axis
energia_normalizada = true;         % false = E in energy units; true = E / <E> of each trial (shape only)
energia_dist_juntas = false;        % true = translation, rotation and total on one axes; false = one panel each

% ---- G: piso sin contacto (figuras 6, 7, 9, 13, 14, 15) ----
G_minimo_cuentas    = 0.5;          % G floor of each trial = this many ADC counts x its K (1 count = 0.43 uS with R_FB 10 kOhm,
                                    % 0.086 uS with 50 kOhm). Below it the 50 ms mean is ADC noise, not conductance: 'no contact'
G_bajo_piso         = 'cero';       % G under the floor: 'cero' = set to 0 (removes the day-dependent noise floor from the
                                    % averages and from dG); 'excluir' = left as measured and out of the log axes

% ---- ΔG = G(t) - G(t - ΔT) (figuras 9a y 9b) ----
deltaT_asim         = [];           % window of figure 9b [s]; [] = the one that maximises the asymmetry of the set
rango_deltaT_asim   = [0.05 15];    % where that window is searched [s] (the asymmetry curves go from 0.05 to 15 s)
normalizar_dG_asim  = false;        % figure 9b: false = dG in uS; true = (dG - mean) / sigma (shape only)
deltaT              = 2.5;          % window of figures 10 and 11 (commented) [s]

% ---- Histograma 2D de V vs G (figura 13) ----
norm_2d             = 'total';      % colours: 'total' = fraction of ALL the frames of the trial; 'contacto' = of the frames with contact
celdas_2d           = [25 20];      % cells [G V]: fewer cells = more frames per cell = less Poisson noise
min_cuadros_2d      = 1;            % cells with fewer frames than this are left empty (1 = draw every non-empty cell)

% ---- Atasco vs libre (figuras 14 y 15, como Colantuono et al., PRE 2026) ----
% Two thresholds, both the same for every trial: "umbral" (manual, above) and one estimated from all the trials.
k_umbral            = 2;            % estimated threshold = 10^(mode - k_umbral * sigma) of log10(Vs); sigma = width above the mode
suav_estado         = 5;            % moving average of V before classifying (Vs) [s]
dur_min_estado      = 0;            % jam / free stretches shorter than this are left out [s] (the paper uses tau_th = 5 s)
deltaT_estado       = 2.5;          % window of the dG histograms of figure 15 [s]

% ---- Aspecto de las figuras (MATLAB defaults for this session) ----
% Light theme even if MATLAB uses the dark one (R2025a+: every new figure is switched with theme(f, 'light')).
if exist('theme', 'file'), set(groot, 'defaultFigureCreateFcn', @(f, ~) theme(f, 'light')); end
set(groot, 'defaultFigureColor', 'w', 'defaultFigureUnits', 'centimeters', 'defaultFigurePosition', [2 2 17 9], ...
    'defaultAxesFontSize', 10, 'defaultAxesTickDir', 'out', 'defaultAxesBox', 'off', ...
    'defaultAxesXGrid', 'on', 'defaultAxesYGrid', 'on', 'defaultLineLineWidth', 1.3, ...
    'defaultLegendBox', 'off', 'defaultLegendInterpreter', 'none', 'defaultLegendLocation', 'northeast');
% (not 'best': with hundreds of thousands of points MATLAB takes very long to place the legend)

%% ============================================ DATOS ============================================

%% Datos (se leen de nuevo solo si cambió "ensayos" o "duracion_min")
% Usa: ensayos, duracion_min, linea_por_modo, G_minimo_cuentas, G_bajo_piso, masa_g, diametro_mm, k_inercia, rango_deltaT_asim
if ~exist('E', 'var') || ~exist('E_pedido', 'var') || ~isequal(E_pedido, {ensayos, duracion_min}) || ~isfield(E, 'etiqueta') || ~isfield(E, 'w2') || isfield(E, 'G_offset')   % G_offset: G shifted by an old version
    E = cargar_datos(ensayos, duracion_min * 60);
    E_pedido = {ensayos, duracion_min};
end
n = numel(E);  nombres = {E.codigo};  et = {E.etiqueta};   % codes (files, console) / readable names (legends, titles)
estilos = cargar_datos('estilos');  leyenda = cargar_datos('leyenda');
[colores, lineas, marcas] = estilos(E, linea_por_modo);   % colour family / line style / marker per mode
% Panels (figures 5 and 13): one row per mode, trials in date order; 'flow' if a mode has more than 4 trials
[~, ~, grupo] = unique({E.modo}, 'stable');  grupo = grupo(:)';
col = arrayfun(@(i) nnz(grupo(1:i) == grupo(i)), 1:n);
filas = max(grupo);  columnas = max(col);  por_fila = columnas <= 4;
panel = (grupo - 1) * columnas + col;                % tile of every trial in the filas x columnas grid
fprintf('Orden: %s\n', strjoin(strcat({E.modo}, {': '}, nombres), ' | '));
% G floor of every trial [uS] (1 x n, NaN without sensor log) from the R_FEEDBACK of calibracion.csv (via E.K),
% so it is the same number of ADC counts whatever the resistor; fraction of the valid samples below it
G_piso = G_minimo_cuentas * [E.K];
sin_contacto = nan(1, n);
for i = 1:n
    g = E(i).G(isfinite(E(i).G));
    if isempty(g), continue; end
    sin_contacto(i) = mean(g < G_piso(i));
    fprintf('%s: piso de G %.3g µS (%g cuenta x K = %.4f µS/cuenta); %.1f %% de las muestras debajo (sin contacto)\n', ...
            nombres{i}, G_piso(i), G_minimo_cuentas, E(i).K, 100 * sin_contacto(i));
end
% G_bajo_piso: always rebuilt from the measured G, so switching the setting and re-running this section is enough
if ~isfield(E, 'G_medido'), [E.G_medido] = E.G;  [E.G_cuadro_medido] = E.G_cuadro; end
for i = 1:n
    E(i).G = E(i).G_medido;  E(i).G_cuadro = E(i).G_cuadro_medido;
    if strcmp(G_bajo_piso, 'cero')                  % NaN (outside the analysed spans) stays NaN
        E(i).G(E(i).G < G_piso(i)) = 0;  E(i).G_cuadro(E(i).G_cuadro < G_piso(i)) = 0;
    end
end
hay_G = ~arrayfun(@(e) isempty(e.G), E);
G_max = max(arrayfun(@(e) max([e.G; 0]), E));
for i = 1:n
    fprintf('%s: R_FEEDBACK %g ohm (calibracion.csv); el firmware calculó con %.0f ohm -> G x%.3g del log; desfase %.2f s\n', ...
            nombres{i}, E(i).R_lista, E(i).R_firmware, E(i).R_firmware / E(i).R_lista, E(i).desfase);
end
% Kinetic energy per frame, summed over the robots (figures 4b and 4c). masa_g = 0 -> per unit mass:
% mm^2/s^2 = uJ/kg; with masa_g, m[g] * mm^2/s^2 = nJ
if masa_g > 0, fe = masa_g;  u_tex = 'nJ';  u_txt = 'nJ'; else, fe = 1;  u_tex = '\muJ/kg';  u_txt = 'µJ/kg'; end
Ec_tras = arrayfun(@(e) fe * e.N .* e.v2 / 2, E, 'UniformOutput', false);
Ec_rot  = arrayfun(@(e) fe * e.N .* k_inercia * (diametro_mm / 2) ^ 2 .* e.w2 / 2, E, 'UniformOutput', false);
% Asymmetry of dG vs window for every trial (figures 8b and 9). Only recomputed when the trials change.
if ~exist('asim', 'var') || ~isequal(asim.clave, {nombres, duracion_min, G_bajo_piso, G_minimo_cuentas})
    t0 = tic;  fprintf('Asimetría de ΔG vs ΔT... ');
    asim = struct('clave', {{nombres, duracion_min, G_bajo_piso, G_minimo_cuentas}}, 'dT', 0.05:0.05:15);
    asim.s = nan(n, numel(asim.dT));                  % rows = trials, NaN without sensor log
    for i = find(hay_G)
        L = max(round(asim.dT / E(i).paso), 1);       % lags in samples
        asim.s(i, :) = arrayfun(@(l) skewness(rmmissing(E(i).G(l + 1:end) - E(i).G(1:end - l)), 0), L);   % 0 = bias-corrected
    end
    fprintf('%.1f s\n', toc(t0));
end
salida = fullfile(E(1).raiz, 'informes', 'figuras', 'matlab_figuras');
sufijo = ['__' strjoin(nombres, '-')];
if strlength(sufijo) > 112, sufijo = sprintf('__%densayos_%s_a_%s', n, nombres{1}, nombres{end}); end
if guardar && ~isfolder(salida), mkdir(salida); end
exportar = cargar_datos('exportar');               % saves one figure in every format of "formatos"
guardar_fig = @(nombre) exportar(gcf, fullfile(salida, [nombre sufijo]), formatos, resolucion);

% %% 0. R_FEEDBACK: calibracion.csv vs la que usó el firmware, en todos los registros de crudos/
% t0 = tic;  fprintf('%s... ', '0. R_FEEDBACK');
% % G_lista_sobre_G_firmware = by how much G changes with respect to the G the firmware logged.
% % The firmware value is the constant it was programmed with: it does not measure the resistor on the board.
% if ~exist('R_feedback', 'var'), R_feedback = cargar_datos('R_feedback'); end   % "clear R_feedback" to read the logs again
% fprintf('%.1f s\n', toc(t0));  disp(R_feedback)

%% ===================================== VELOCIDAD Y ENERGÍA =====================================
% Figuras 1 a 5: V media, su distribución, energía cinética y ocupación del recinto.

%% 1. V media vs tiempo
% Usa: suav, umbral
t0 = tic;  fprintf('%s... ', '1. V media vs tiempo');
figure('Name', 'V media vs tiempo');  hold on
for i = 1:n
    plot(E(i).t / 60, movmean(E(i).V, suav, 'omitnan', 'SamplePoints', E(i).t), 'Color', colores(i, :), 'LineStyle', lineas{i}, 'Tag', nombres{i}, 'DisplayName', et{i});
end
yline(umbral, '--', 'umbral', 'HandleVisibility', 'off');
xlim([0 min(duracion_min, max(vertcat(E.t)) / 60)]);
xlabel('t [min]');  ylabel('V_{media} [mm/s]');  leyenda(gca);
if guardar, guardar_fig('velocidad_tiempo'); end
drawnow;  fprintf('%.1f s\n', toc(t0));

%% 2. Distribución de V media
t0 = tic;  fprintf('%s... ', '2. Distribución de V media');
% 'pdf' = density (integrates to 1); 'probability' = fraction of the frames in each bin
figure('Name', 'Distribucion de V');  hold on
bordes = linspace(0, max(vertcat(E.V)), 61);
for i = 1:n
    histogram(E(i).V, bordes, 'Normalization', 'pdf', 'DisplayStyle', 'stairs', 'LineWidth', 1.3, ...
              'EdgeColor', colores(i, :), 'LineStyle', lineas{i}, 'Tag', nombres{i}, 'DisplayName', et{i});
end
set(gca, 'YScale', 'log');  xlabel('V_{media} [mm/s]');  ylabel('P(V) [s/mm]');  leyenda(gca);
if guardar, guardar_fig('distribucion_velocidad'); end
drawnow;  fprintf('%.1f s\n', toc(t0));

%% 3. 1 - F(V / <V>): cola de la distribución (solo la forma, sin la escala)
t0 = tic;  fprintf('%s... ', '3. 1 - F(V / <V>)');
figure('Name', '1 - F(V)');  hold on
for i = 1:n
    v = sort(rmmissing(E(i).V));
    plot(v / mean(v), (numel(v):-1:1) / numel(v), 'Color', colores(i, :), 'LineStyle', lineas{i}, 'Tag', nombres{i}, 'DisplayName', et{i});
end
set(gca, 'YScale', 'log');  xlabel('V / \langle V \rangle');  ylabel('P(V \geq v)');  leyenda(gca);
if guardar, guardar_fig('ccdf_velocidad'); end
drawnow;  fprintf('%.1f s\n', toc(t0));

% %% 4. Distribución de ω (> 0 antihorario)
% t0 = tic;  fprintf('%s... ', '4. Distribución de ω');
% figure('Name', 'Distribucion de omega');  hold on
% for i = 1:n
%     histogram(E(i).omega, -60:2:60, 'Normalization', 'pdf', 'DisplayStyle', 'stairs', 'LineWidth', 1.3, ...
%               'EdgeColor', colores(i, :), 'LineStyle', lineas{i}, 'Tag', nombres{i}, 'DisplayName', et{i});
%     fprintf('%s (%s): ω media %.2f °/s, %.0f %% del tiempo antihorario\n', nombres{i}, E(i).modo_nombre, mean(E(i).omega), 100 * mean(E(i).omega > 0));
% end
% xline(0, 'HandleVisibility', 'off');  xlabel('\omega [°/s]');  ylabel('densidad [s/°]');  leyenda(gca);
% if guardar, guardar_fig('distribucion_omega'); end
% drawnow;  fprintf('%.1f s\n', toc(t0));

% %% 4b. Energía cinética vs tiempo: traslación, rotación y total
% t0 = tic;  fprintf('%s... ', '4b. Energía cinética');
% % Per frame, summed over the robots (König: the orbit of a robot around the arena is already inside its v):
% %   E_tras = sum(1/2 m v^2),  E_rot = sum(1/2 k m R^2 w^2),  E_total = E_tras + E_rot
% % Every robot of the frame enters (interpolated rows too), as in V media. masa_g = 0 -> per unit mass:
% % mm^2/s^2 = uJ/kg; with masa_g, m[g] * mm^2/s^2 = nJ. The three panels share both axes so that the size of
% % rotation and translation can be compared directly.
% figure('Name', 'Energia cinetica', 'Position', [2 2 17 18]);
% tl = tiledlayout(3, 1, 'TileSpacing', 'compact');
% titulos = {'Traslación', 'Rotación', 'Total'};  ax = gobjects(1, 3);
% for p = 1:3, ax(p) = nexttile(tl);  hold(ax(p), 'on');  title(ax(p), titulos{p}); end
% for i = 1:n
%     Et = Ec_tras{i};  Er = Ec_rot{i};               % from the Datos section
%     curvas = {Et, Er, Et + Er};
%     for p = 1:3
%         plot(ax(p), E(i).t / 60, movmean(curvas{p}, suav, 'omitnan', 'SamplePoints', E(i).t), ...
%              'Color', colores(i, :), 'LineStyle', lineas{i}, 'Tag', nombres{i}, 'DisplayName', et{i});
%     end
%     fprintf('%s: E_tras %.3g, E_rot %.3g, E_total %.3g %s (medias); E_rot/E_tras = %.2f\n', nombres{i}, ...
%             mean(Et, 'omitnan'), mean(Er, 'omitnan'), mean(Et + Er, 'omitnan'), u_txt, mean(Er, 'omitnan') / mean(Et, 'omitnan'));
% end
% if energia_log, set(ax, 'YScale', 'log'); end
% linkaxes(ax, 'xy');  xlim(ax(1), [0 min(duracion_min, max(vertcat(E.t)) / 60)]);
% xticklabels(ax(1:2), {});
% xlabel(tl, 't [min]');  ylabel(tl, sprintf('E_c [%s]', u_tex));
% leyenda(ax(1));  ax(1).Legend.Layout.Tile = 'east';
% if guardar, guardar_fig('energia_cinetica'); end
% drawnow;  fprintf('%.1f s\n', toc(t0));

%% 4c. Distribución de la energía cinética por cuadro (sin el tiempo)
% Usa: masa_g, diametro_mm, k_inercia (en Datos), energia_normalizada, energia_dist_juntas
t0 = tic;  fprintf('%s... ', '4c. Distribución de la energía cinética');
% Every frame is one sample, without the moving average (smoothing would narrow the distribution). Log-spaced bins
% common to every trial and panel (0.1-99.9 percentiles of all the values); 'probability' = fraction of the frames
% in each bin, so with log bins the curves read as frames per decade. energia_normalizada = true: E / <E> of each
% trial and component, which removes the overall energy level (it changes between dates) and leaves only the shape.
% energia_dist_juntas = true: the three components on one axes (colour = trial, line = component: translation
% dotted, rotation dashed, total solid; here the line style no longer marks the mode, the colour family still does);
% false: one panel per component.
comp = {'Traslación', 'Rotación', 'Total'};  X = cell(3, n);
trazo_comp = {':', '--', '-'};
for i = 1:n
    X(:, i) = {Ec_tras{i}; Ec_rot{i}; Ec_tras{i} + Ec_rot{i}};
    if energia_normalizada, X(:, i) = cellfun(@(x) x / mean(x, 'omitnan'), X(:, i), 'UniformOutput', false); end
    q = cellfun(@(x) prctile(x, [10 50 90]), X(:, i), 'UniformOutput', false);
    fprintf('%s: mediana [p10 p90]  tras %.3g [%.3g %.3g]  rot %.3g [%.3g %.3g]  total %.3g [%.3g %.3g]\n', ...
            nombres{i}, q{1}([2 1 3]), q{2}([2 1 3]), q{3}([2 1 3]));
end
todo = vertcat(X{:});  todo = todo(todo > 0 & isfinite(todo));
bordes_E = logspace(log10(prctile(todo, 0.1)), log10(prctile(todo, 99.9)), 61);
if energia_dist_juntas
    figure('Name', 'Distribucion de energia cinetica');  hold on
    for i = 1:n
        for p = 1:3
            x = X{p, i};
            h = histogram(x(x > 0), bordes_E, 'Normalization', 'probability', 'DisplayStyle', 'stairs', 'LineWidth', 1.4, ...
                          'EdgeColor', colores(i, :), 'LineStyle', trazo_comp{p}, 'Tag', nombres{i}, ...
                          'DisplayName', sprintf('%s · %s', et{i}, comp{p}));
            if p < 3, h.HandleVisibility = 'off'; end  % one legend entry per trial (the total); components below
        end
        h.DisplayName = et{i};
    end
    for p = 1:3   % legend keys for the line styles (not trials: leyenda puts them last)
        plot(NaN, NaN, 'k', 'LineStyle', trazo_comp{p}, 'LineWidth', 1.4, 'DisplayName', comp{p});
    end
    set(gca, 'XScale', 'log');
    if energia_normalizada, xlabel('E_c / \langle E_c \rangle'); else, xlabel(sprintf('E_c [%s]', u_tex)); end
    ylabel('fracción de los cuadros');  leyenda(gca);
    nombre_fig = 'energia_distribucion_juntas';
else
    figure('Name', 'Distribucion de energia cinetica', 'Position', [2 2 17 18]);
    tl = tiledlayout(3, 1, 'TileSpacing', 'compact');
    ax = gobjects(1, 3);
    for p = 1:3
        ax(p) = nexttile(tl);  hold(ax(p), 'on');  title(ax(p), comp{p});
        for i = 1:n
            x = X{p, i};
            histogram(ax(p), x(x > 0), bordes_E, 'Normalization', 'probability', 'DisplayStyle', 'stairs', 'LineWidth', 1.3, ...
                      'EdgeColor', colores(i, :), 'LineStyle', lineas{i}, 'Tag', nombres{i}, 'DisplayName', et{i});
        end
    end
    set(ax, 'XScale', 'log');  linkaxes(ax, 'xy');  xticklabels(ax(1:2), {});
    if energia_normalizada, xlabel(tl, 'E_c / \langle E_c \rangle'); else, xlabel(tl, sprintf('E_c [%s]', u_tex)); end
    ylabel(tl, 'fracción de los cuadros');
    leyenda(ax(1));  ax(1).Legend.Layout.Tile = 'east';
    nombre_fig = 'energia_distribucion';
end
if energia_normalizada, nombre_fig = [nombre_fig '_normalizada']; end
if guardar, guardar_fig(nombre_fig); end
drawnow;  fprintf('%.1f s\n', toc(t0));

%% 5. Ocupación del recinto (robots/cm², promedio en el tiempo)
t0 = tic;  fprintf('%s... ', '5. Ocupación del recinto');
figure('Name', 'Ocupacion', 'Position', [2 2 17 11]);
if por_fila, tl = tiledlayout(filas, columnas, 'TileSpacing', 'compact'); else, tl = tiledlayout('flow', 'TileSpacing', 'compact'); end
b = -92.5:5:92.5;                                   % 5 mm cells over the inner diameter (185 mm)
c = (b(1:end - 1) + b(2:end)) / 2 / 10;             % cell centres [cm]
dentro = hypot(c, c') <= 9.25;                      % cells inside the wall (white outside)
todas = [];
for i = 1:n
    if por_fila, nexttile(panel(i)); else, nexttile; end
    N = histcounts2(E(i).x, E(i).y, b, b)' / E(i).nf / 0.25;     % counts / frames / 0.25 cm^2 (rows = y)
    imagesc(c, c, N, 'AlphaData', dentro);  axis xy equal tight
    rectangle('Position', [-9.25 -9.25 18.5 18.5], 'Curvature', 1, 'EdgeColor', [0.3 0.3 0.3]);
    title({et{i}, E(i).modo_nombre}, 'Interpreter', 'none', 'Color', colores(i, :));
    todas = [todas; N(dentro)]; %#ok<AGROW>
end
% One colour scale: 99th percentile of every cell of every trial (a few cells under robots stuck in a jam
% would otherwise push the top up and leave the other panels flat)
set(findobj(gcf, 'Type', 'axes'), 'CLim', [0 prctile(todas, 99)]);
cb = colorbar;  cb.Layout.Tile = 'east';  cb.Label.String = 'robots/cm^2';
xlabel(tl, 'x [cm]');  ylabel(tl, 'y [cm]');
if guardar, guardar_fig('ocupacion'); end
drawnow;  fprintf('%.1f s\n', toc(t0));

%% ============================================== G ==============================================
% Figuras 6 a 13: conductancia del sensor (G), sus incrementos ΔG y su relación con V.

%% 6. G vs tiempo (eje de tiempo del video)
% Usa: suav, G_minimo_cuentas
t0 = tic;  fprintf('%s... ', '6. G vs tiempo');
figure('Name', 'G vs tiempo');  hold on
for i = find(hay_G)
    g = movmean(E(i).G, suav, 'omitnan', 'SamplePoints', E(i).ts);
    g(isnan(E(i).G) | g < G_piso(i)) = NaN;         % outside the analysed spans; below the floor = no contact
    k = 1:round(1 / E(i).paso):numel(g);            % one point per second is enough after the 30 s average
    plot((E(i).ts(k) - E(i).desfase) / 60, g(k), 'Color', colores(i, :), 'LineStyle', lineas{i}, 'Tag', nombres{i}, 'DisplayName', et{i});
end
for gp = unique(G_piso(hay_G))                     % floor of 1 count (one line per R_FEEDBACK); below = not drawn
    yline(gp, ':', sprintf('piso %.2g µS', gp), 'HandleVisibility', 'off', 'LabelHorizontalAlignment', 'left');
end
set(gca, 'YScale', 'log');  xlim([0 min(duracion_min, max(vertcat(E.t)) / 60)]);  xlabel('t [min]');  ylabel('G [\muS]');  leyenda(gca);
if guardar, guardar_fig('G_tiempo'); end
drawnow;  fprintf('%.1f s\n', toc(t0));

%% 7. P(G ≥ g), con G dividida por su media
% Usa: G_minimo_cuentas
t0 = tic;  fprintf('%s... ', '7. P(G ≥ g), con G dividida por su media');
figure('Name', 'Supervivencia de G');  hold on
for i = find(hay_G)
    g = sort(rmmissing(E(i).G));  p = (numel(g):-1:1)' / numel(g);
    m = numel(g);                                   % ~2000 points: evenly spread + dense in the tail (largest G)
    k = unique([round(linspace(1, m, 1000)), m + 1 - round(logspace(0, log10(m), 1000))]);
    k = k(g(k) >= G_piso(i));                       % below the floor = no contact (P still over every sample)
    plot(g(k), p(k), 'Color', colores(i, :), 'LineStyle', lineas{i}, 'Tag', nombres{i}, 'DisplayName', et{i});
end
set(gca, 'YScale', 'log');  xlabel('g');  ylabel('P(G \geq g)');  leyenda(gca);
if guardar, guardar_fig('G_supervivencia'); end
drawnow;  fprintf('%.1f s\n', toc(t0));

% %% 8. Histograma de G (clases logarítmicas)
% t0 = tic;  fprintf('%s... ', '8. Histograma de G');
% figure('Name', 'Histograma de G');  hold on
% for i = find(hay_G)
%     histogram(E(i).G, logspace(log10(min(G_piso(hay_G))), log10(G_max), 41), 'Normalization', 'pdf', 'DisplayStyle', 'stairs', ...
%               'LineWidth', 1.3, 'EdgeColor', colores(i, :), 'LineStyle', lineas{i}, 'Tag', nombres{i}, 'DisplayName', et{i});
% end
% set(gca, 'Xscale', 'log', 'YScale', 'log');  xlabel('G [\muS]');  ylabel('densidad [1/\muS]');  leyenda(gca);
% if guardar, guardar_fig('G_histograma'); end
% drawnow;  fprintf('%.1f s\n', toc(t0));

%% 9a. Asimetría de ΔG = G(t) - G(t - ΔT) en función de ΔT
% Usa: deltaT_asim, rango_deltaT_asim
t0 = tic;  fprintf('%s... ', '9. Asimetría de ΔG = G(t) - G(t - ΔT) en función de ΔT');
% Curves from the Datos section; dotted line = window of figure 8b
% dT_asim = window that maximises the mean |asymmetry of dG| over the trials (one value for all of them)
asim_media = mean(abs(asim.s(hay_G, :)), 1, 'omitnan');
asim_media(asim.dT < rango_deltaT_asim(1) | asim.dT > rango_deltaT_asim(2)) = NaN;
[asim_max, j] = max(asim_media);  dT_asim = asim.dT(j);
if ~isempty(deltaT_asim), dT_asim = deltaT_asim; end
figure('Name', 'Asimetria de Delta G');  hold on
for i = find(hay_G)
    plot(asim.dT, asim.s(i, :), 'Color', colores(i, :), 'LineStyle', lineas{i}, 'Tag', nombres{i}, 'DisplayName', et{i});
end
xline(dT_asim, ':', sprintf('\\DeltaT = %.2f s', dT_asim), 'HandleVisibility', 'off');
yline(0, 'HandleVisibility', 'off');  xlabel('\DeltaT [s]');  ylabel('asimetría de \DeltaG');  leyenda(gca);
if guardar, guardar_fig('asimetria_deltaT'); end
drawnow;  fprintf('%.1f s\n', toc(t0));

%% 9b. Histograma de ΔG con el ΔT de máxima asimetría del conjunto (ventana fija)
% Usa: deltaT_asim, rango_deltaT_asim, normalizar_dG_asim
t0 = tic;  fprintf('%s... ', '8b. Histograma de ΔG (ΔT de máxima asimetría)');
% Criterion: mean over the trials of |asymmetry of dG| (|.| so that negative and positive asymmetries do not
% cancel; per-trial asymmetry does not depend on the uS scale of each trial). The same window for every trial.
% dT_asim = window that maximises the mean |asymmetry of dG| over the trials (one value for all of them)
asim_media = mean(abs(asim.s(hay_G, :)), 1, 'omitnan');
asim_media(asim.dT < rango_deltaT_asim(1) | asim.dT > rango_deltaT_asim(2)) = NaN;
[asim_max, j] = max(asim_media);  dT_asim = asim.dT(j);
if ~isempty(deltaT_asim), dT_asim = deltaT_asim; end
if isempty(deltaT_asim)
    fprintf('ΔT de máxima asimetría del conjunto = %.2f s (media de |asimetría| = %.2f)\n', dT_asim, asim_max);
else
    fprintf('ΔT fijado en Ajustes = %.2f s (el máximo del conjunto está en %.2f s)\n', dT_asim, asim.dT(j));
end
figure('Name', 'Histograma de Delta G (asimetria maxima)');  hold on
D = cell(1, n);  sigma = nan(1, n);
for i = find(hay_G)
    L = max(round(dT_asim / E(i).paso), 1);
    D{i} = rmmissing(E(i).G(L + 1:end) - E(i).G(1:end - L));
    sigma(i) = std(D{i});                           % in uS, also when the plot is normalised
    if normalizar_dG_asim, D{i} = (D{i} - mean(D{i})) / sigma(i); end
end
lim = max(cellfun(@(d) prctile(abs([d; 0]), 99.9), D(hay_G)));   % common bins: 99.9 % of |dG| of every trial
for i = find(hay_G)
    histogram(D{i}, linspace(-lim, lim, 81), 'Normalization', 'pdf', 'DisplayStyle', 'stairs', 'LineWidth', 1.3, ...
        'EdgeColor', colores(i, :), 'LineStyle', lineas{i}, ...
        'Tag', nombres{i}, 'DisplayName', sprintf('%s (asimetría %.2f; σ = %.3g µS)', et{i}, skewness(D{i}, 0), sigma(i)));
end
if normalizar_dG_asim
    z = linspace(-lim, lim, 400);
    plot(z, normpdf(z), 'k:', 'LineWidth', 1.6, 'DisplayName', 'normal');
    xlabel(sprintf('\\DeltaG / \\sigma  (\\DeltaT = %.2f s, máxima asimetría)', dT_asim));  ylabel('densidad');
else
    xlabel(sprintf('\\DeltaG [\\muS]  (\\DeltaT = %.2f s, máxima asimetría)', dT_asim));  ylabel('densidad [1/\muS]');
end
set(gca, 'YScale', 'log');  leyenda(gca);
if guardar, guardar_fig('deltaG_histograma_asimetria_max'); end
drawnow;  fprintf('%.1f s\n', toc(t0));

% %% 10. Distribución de ΔG / σ para un ΔT (colas comparadas con la normal)
% t0 = tic;  fprintf('%s... ', '10. Distribución de ΔG / σ para un ΔT');
% figure('Name', 'Distribucion de Delta G');  hold on
% z = -10:0.25:10;
% for i = find(hay_G)
%     L = round(deltaT / E(i).paso);
%     d = rmmissing(E(i).G(L + 1:end) - E(i).G(1:end - L));
%     histogram((d - mean(d)) / std(d), z, 'Normalization', 'pdf', 'DisplayStyle', 'stairs', 'LineWidth', 1.3, ...
%               'EdgeColor', colores(i, :), 'LineStyle', lineas{i}, 'Tag', nombres{i}, ...
%               'DisplayName', sprintf('%s (asimetría %.2f; σ = %.3g µS)', et{i}, skewness(d, 0), std(d)));
% end
% plot(z, normpdf(z), 'k:', 'LineWidth', 1.6, 'DisplayName', 'normal');   % dotted: dashed is AL
% set(gca, 'YScale', 'log');  xlabel(sprintf('\\DeltaG / \\sigma  (\\DeltaT = %g s)', deltaT));  ylabel('densidad');  leyenda(gca);
% if guardar, guardar_fig('deltaG_distribucion'); end
% drawnow;  fprintf('%.1f s\n', toc(t0));
% 
% %% 11. Distribución de ΔG en µS
% t0 = tic;  fprintf('%s... ', '11. Distribución de ΔG en µS');
% figure('Name', 'Distribucion de Delta G sin normalizar');  hold on
% D = cell(1, n);
% for i = find(hay_G)
%     L = round(deltaT / E(i).paso);
%     D{i} = rmmissing(E(i).G(L + 1:end) - E(i).G(1:end - L));
% end
% lim = max(cellfun(@(d) prctile(abs([d; 0]), 99.9), D(hay_G)));   % common bins: 99.9 % of |dG| of every trial
% bordes_dG = linspace(-lim, lim, 81);
% for i = find(hay_G)
%     histogram(D{i}, bordes_dG, 'Normalization', 'pdf', 'DisplayStyle', 'stairs', 'LineWidth', 1.3, ...
%               'EdgeColor', colores(i, :), 'LineStyle', lineas{i}, 'Tag', nombres{i}, ...
%               'DisplayName', sprintf('%s (asimetría %.2f; σ = %.3g µS)', et{i}, skewness(D{i}, 0), std(D{i})));
% end
% set(gca, 'YScale', 'log');  xlabel(sprintf('\\DeltaG [\\muS]  (\\DeltaT = %g s)', deltaT));  ylabel('densidad [1/\muS]');  leyenda(gca);
% if guardar, guardar_fig('deltaG_distribucion_uS'); end
% drawnow;  fprintf('%.1f s\n', toc(t0));
% 
% %% 12. G mediana por clase de V media (ρ de Spearman)
% t0 = tic;  fprintf('%s... ', '12. G mediana por clase de V media');
% suav_vg = 15;                                       % smoothing of V and G for this figure [s]
% figure('Name', 'G vs V media');  hold on
% bordes = linspace(0, max(vertcat(E.V)), 26);
% for i = find(hay_G)
%     v = movmean(E(i).V, suav_vg, 'omitnan', 'SamplePoints', E(i).t);
%     g = movmean(E(i).G_cuadro, suav_vg, 'omitnan', 'SamplePoints', E(i).t);
%     ok = isfinite(v) & isfinite(E(i).G_cuadro) & g >= G_piso(i);
%     v = v(ok);  g = g(ok);  k = discretize(v, bordes);  q = ~isnan(k);
%     mediana = accumarray(k(q), g(q), [numel(bordes) - 1, 1], @median, NaN);
%     mediana(accumarray(k(q), 1, [numel(bordes) - 1, 1]) < 30) = NaN;      % at least 30 frames (10 s) per class
%     plot(bordes(1:end - 1) + diff(bordes) / 2, mediana, 'LineStyle', lineas{i}, 'Marker', marcas{i}, 'Color', colores(i, :), 'MarkerFaceColor', colores(i, :), ...
%          'MarkerSize', 4, 'Tag', nombres{i}, 'DisplayName', sprintf('%s (ρ = %.2f)', et{i}, corr(v, g, 'Type', 'Spearman')));
% end
% xline(umbral, '--', 'umbral', 'HandleVisibility', 'off');
% set(gca, 'YScale', 'log');  xlabel('V_{media} [mm/s]');  ylabel('G [\muS]');  leyenda(gca);
% if guardar, guardar_fig('G_vs_velocidad'); end
% drawnow;  fprintf('%.1f s\n', toc(t0));

%% 13. Histograma 2D de V media vs G (un panel por ensayo, misma escala de color)
% Usa: norm_2d, celdas_2d, min_cuadros_2d, umbral, G_minimo_cuentas
t0 = tic;  fprintf('%s... ', '13. Histograma 2D de V media vs G');
figure('Name', 'Histograma 2D V vs G', 'Position', [2 2 17 11]);
if por_fila, tl = tiledlayout(filas, columnas, 'TileSpacing', 'compact'); else, tl = tiledlayout('flow', 'TileSpacing', 'compact'); end
% Counts per cell / denominator of norm_2d; cells under min_cuadros_2d frames are emptied (ShowEmptyBins off).
% Column S/C (sin contacto, G under the floor of the trial): one cell wide, one empty cell left of the lowest floor;
% its G position is nominal (no G value is meant). Dotted line = floor of the trial.
bordes_G = logspace(log10(min(G_piso(hay_G))), log10(G_max), celdas_2d(1) + 1);
bordes_V = linspace(0, max(vertcat(E.V)), celdas_2d(2) + 1);
w = log10(bordes_G(2) / bordes_G(1));               % cell width [decades]
bordes_X = [bordes_G(1) * 10 .^ (-w * [2 1]), bordes_G];   % S/C column, empty gap cell, then the real cells
x_sc = sqrt(bordes_X(1) * bordes_X(2));             % centre of the S/C column (tick)
for i = find(hay_G)
    if por_fila, nexttile(panel(i)); else, nexttile; end
    validos = isfinite(E(i).G_cuadro_medido) & isfinite(E(i).V);   % frames with sensor and speed
    ok = validos & E(i).G_cuadro_medido >= G_piso(i);               % frames with contact
    sc = 1 - nnz(ok) / nnz(validos);
    C = [histcounts(E(i).V(validos & ~ok), bordes_V); zeros(1, celdas_2d(2)); ...
         histcounts2(E(i).G_cuadro_medido(ok), E(i).V(ok), bordes_G, bordes_V)];
    C(C < min_cuadros_2d) = 0;
    if strcmp(norm_2d, 'total'), C = C / nnz(validos); else, C = C / nnz(ok); C(1, :) = 0; end   % 'contacto': no S/C
    histogram2('XBinEdges', bordes_X, 'YBinEdges', bordes_V, 'BinCounts', C, 'DisplayStyle', 'tile', ...
               'ShowEmptyBins', 'off', 'EdgeColor', 'none');
    set(gca, 'XScale', 'log', 'ColorScale', 'log');
    xline(G_piso(i), ':', 'HandleVisibility', 'off');
    yline(umbral, '--', 'umbral');
    title({et{i}, sprintf('sin contacto: %.0f %% de los cuadros', 100 * sc)}, ...
          'Interpreter', 'none', 'Color', colores(i, :));
end
h = findobj(gcf, 'Type', 'histogram2');  valores = cat(3, h.Values);
d = ceil(log10(bordes_G(1))):floor(log10(bordes_G(end)));     % decades inside the real G range
set(findobj(gcf, 'Type', 'axes'), 'CLim', [min(valores(valores > 0)) max(valores(:))], ...
    'XLim', bordes_X([1 end]), 'XTick', [x_sc, 10 .^ d], ...  % same G axis in every panel
    'XTickLabel', [{'S/C'}, arrayfun(@(k) sprintf('10^{%d}', k), d, 'UniformOutput', false)]);
cb = colorbar;  cb.Layout.Tile = 'east';
if strcmp(norm_2d, 'total'), cb.Label.String = 'fracción de todos los cuadros'; else, cb.Label.String = 'fracción de los cuadros con contacto'; end
xlabel(tl, sprintf('G [\\muS]   (S/C = sin contacto: < %g cuenta del ADC)', G_minimo_cuentas));  ylabel(tl, 'V_{media} [mm/s]');
if guardar, guardar_fig(['histograma2d_V_G_' norm_2d]); end
drawnow;  fprintf('%.1f s\n', toc(t0));

%% ======================================= ATASCO VS LIBRE =======================================
% Como Colantuono et al., PRE 2026 (figs. 3 y 4): G con los robots atascados (G_c) vs en flujo libre (G_b).
% Cada cuadro es 'atasco' si la V media suavizada (Vs) está debajo del umbral y 'libre' si está arriba; los tramos
% más cortos que dur_min_estado no se usan. Cada muestra del sensor toma el estado de su cuadro. Dos umbrales, los
% dos iguales para todos los ensayos: el manual (umbral) y uno estimado con la V de todos los ensayos juntos.

%% Atasco vs libre: clasificación (correr antes de 14 y 15, y de nuevo si cambian sus ajustes)
% Usa: umbral, k_umbral, suav_estado, dur_min_estado
estados = cargar_datos('estados');  incrementos = cargar_datos('incrementos');
clas = estados(E, umbral, k_umbral, suav_estado, dur_min_estado);
for c = 1:2
    for i = 1:n
        fprintf('%s | umbral %s: atasco %.1f %%, libre %.1f %% del tiempo\n', nombres{i}, clas(c).nombre, ...
                100 * mean(clas(c).est{i} == 1), 100 * mean(clas(c).est{i} == 2));
    end
end

%% 14. P(G ≥ g) en libre (G_b) y en atasco (G_c), y cuantiles de G_c vs G_b
% Usa: la clasificación de arriba. Filas: umbral manual / estimado. Q-Q: sobre la línea de trazos las dos
% distribuciones son iguales; por encima, los robots empujan más fuerte la pared cuando están atascados.
t0 = tic;  fprintf('%s... ', '14. G en atasco vs libre');
p_qq = [0.5:0.5:99, 99.1:0.1:99.9];
figure('Name', 'G atasco vs libre', 'Position', [2 2 17 12]);
tl = tiledlayout(2, 3, 'TileSpacing', 'compact');  ax = gobjects(2, 3);
for c = 1:2
    for p = 1:3, ax(c, p) = nexttile(tl);  hold on; end
    tope = 0;
    for i = find(hay_G)
        Gc = rmmissing(E(i).G(clas(c).est_s{i} == 1));  Gb = rmmissing(E(i).G(clas(c).est_s{i} == 2));
        if numel(Gc) < 100 || numel(Gb) < 100, continue; end   % too few samples in one of the two states
        estilo = {'Color', colores(i, :), 'LineStyle', lineas{i}, 'Tag', nombres{i}, 'DisplayName', et{i}};
        F = {Gb, Gc};
        for p = 1:2
            g = sort(F{p});
            plot(ax(c, p), g, (numel(g):-1:1)' / numel(g), estilo{:});
        end
        qb = prctile(Gb, p_qq);  qc = prctile(Gc, p_qq);
        plot(ax(c, 3), qb, qc, estilo{:});
        tope = max([tope, qb, qc]);
        fprintf('\n  %s | %s: <G_c> = %.3g µS, <G_b> = %.3g µS (x%.2f)', nombres{i}, clas(c).nombre, mean(Gc), mean(Gb), mean(Gc) / mean(Gb));
    end
    plot(ax(c, 3), [0 tope], [0 tope], 'k--', 'HandleVisibility', 'off');
    ylabel(ax(c, 1), {['umbral ' clas(c).nombre], 'P(G \geq g)'});  ylabel(ax(c, 3), 'cuantiles de G_c [\muS]');
end
set(ax(:, 1:2), 'YScale', 'log');  linkaxes(ax(:, 1:2), 'xy');
title(ax(1, 1), 'libre (G_b)');  title(ax(1, 2), 'atasco (G_c)');  title(ax(1, 3), 'Q-Q');
xlabel(ax(2, 1), 'g [\muS]');  xlabel(ax(2, 2), 'g [\muS]');  xlabel(ax(2, 3), 'cuantiles de G_b [\muS]');
leyenda(ax(1, 3));  ax(1, 3).Legend.Layout.Tile = 'east';
if guardar, guardar_fig('atasco_G'); end
drawnow;  fprintf('\n%.1f s\n', toc(t0));

%% 15. Histograma de ΔG = G(t + ΔT) - G(t) en atasco y en libre
% Usa: deltaT_estado y la clasificación de arriba. Los dos extremos de cada ΔG en el mismo tramo.
% Asimetría negativa = subidas lentas y caídas bruscas.
t0 = tic;  fprintf('%s... ', '15. ΔG en atasco vs libre');
D = cell(2, 2, n);
for c = 1:2
    for i = find(hay_G)
        L = round(deltaT_estado / E(i).paso);
        for s = 1:2, D{c, s, i} = incrementos(E(i).G, L, clas(c).est_s{i}, clas(c).tramo_s{i}, s); end
    end
end
lim = prctile(abs(vertcat(D{:}, 0)), 99.9);        % common bins: 99.9 % of every |dG|
estado = {'atasco', 'libre'};
figure('Name', 'Delta G atasco vs libre', 'Position', [2 2 17 13]);
tl = tiledlayout(2, 2, 'TileSpacing', 'compact');  ax = gobjects(2, 2);
for c = 1:2
    for s = 1:2
        ax(c, s) = nexttile(tl);  hold on
        for i = find(hay_G)
            d = D{c, s, i};
            if numel(d) < 100, continue; end
            histogram(d, linspace(-lim, lim, 81), 'Normalization', 'pdf', 'DisplayStyle', 'stairs', 'LineWidth', 1.3, ...
                      'EdgeColor', colores(i, :), 'LineStyle', lineas{i}, 'Tag', nombres{i}, ...
                      'DisplayName', sprintf('%s (asim. %.2f)', et{i}, skewness(d, 0)));
        end
        set(gca, 'YScale', 'log');  title(sprintf('%s · umbral %s', estado{s}, clas(c).nombre), 'FontSize', 9);
        if ~isempty(findobj(gca, 'Type', 'histogram')), leyenda(gca);  ax(c, s).Legend.FontSize = 7; end
    end
end
linkaxes(ax, 'xy');
xlabel(tl, sprintf('\\DeltaG [\\muS]  (\\DeltaT = %g s)', deltaT_estado));  ylabel(tl, 'densidad [1/\muS]');
if guardar, guardar_fig('atasco_deltaG'); end
drawnow;  fprintf('\n%.1f s\n', toc(t0));
