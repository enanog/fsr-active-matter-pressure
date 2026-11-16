%% figuras.m  -  comparación de ensayos: velocidad, giro, ocupación, G y V vs G
% Cada sección (%%) es una figura: Ctrl+Enter corre solo esa sección, F5 corre todas.
% La sección "Datos" lee los ensayos una sola vez y los deja en el workspace (E); las demás solo grafican.
% Los datos salen de datos/video/trayectorias/VP_<código>_robots.csv y datos/presion/crudos/R_<código>.csv,
% procesados como FSRScope (ver cargar_datos.m). Cada ensayo tiene el mismo color en todas las figuras.
% Requiere MATLAB R2020b+ y Statistics and Machine Learning Toolbox (skewness, corr, normpdf, prctile).

clc; clear;

%% Ajustes
ensayos = {};  % part of the codes; {} = pick from a list
suav    = 10;      % moving average of the time plots [s]
umbral  = 0.35;    % jam threshold [mm/s]
deltaT  = 2.5;     % window of dG = G(t) - G(t - deltaT) [s]
duracion_min = 60; % only the first minutes from the start of every video (and the sensor in that window); Inf = all
G_minimo = 1e-2;   % G below this [uS] is not drawn on log axes: there G is just a few ADC steps (quantisation)
guardar = true;   %#ok<*UNRCH> (if guardar ... is not dead code) true: every figure -> informes/figuras/matlab_figuras/<figura>__<códigos>.<formato>
formatos = {                   % one per line; put % in front of a line to switch that format off (Ctrl+R / Ctrl+T)
    '.png'                     % image (uses "resolucion")
    % '.pdf'                     % vector
    % '.svg'                   % vector
    % '.eps'                   % vector
    % '.emf'                   % vector (Word / PowerPoint)
    % '.jpg'                   % image
    % '.tif'                   % image
    % '.fig'                   % MATLAB figure, can be opened and edited again
};
resolucion = 300;  % dpi of the images (.png .jpg .tif)

% Look of every figure (MATLAB defaults for this session). Light theme even if MATLAB uses the dark one
% (R2025a+: every new figure is switched with theme(f, 'light'); older versions are always light).
if exist('theme', 'file'), set(groot, 'defaultFigureCreateFcn', @(f, ~) theme(f, 'light')); end
set(groot, 'defaultFigureColor', 'w', 'defaultFigureUnits', 'centimeters', 'defaultFigurePosition', [2 2 17 9], ...
    'defaultAxesFontSize', 10, 'defaultAxesTickDir', 'out', 'defaultAxesBox', 'off', ...
    'defaultAxesXGrid', 'on', 'defaultAxesYGrid', 'on', 'defaultLineLineWidth', 1.3, ...
    'defaultLegendBox', 'off', 'defaultLegendInterpreter', 'none', 'defaultLegendLocation', 'northeast');
% (not 'best': with hundreds of thousands of points MATLAB takes very long to place the legend)

%% Datos (se leen de nuevo solo si cambió "ensayos" o "duracion_min")
if ~exist('E', 'var') || ~exist('E_pedido', 'var') || ~isequal(E_pedido, {ensayos, duracion_min})
    E = cargar_datos(ensayos, duracion_min * 60);
    E_pedido = {ensayos, duracion_min};
end
n = numel(E);  nombres = {E.codigo};  colores = lines(n);
hay_G = ~arrayfun(@(e) isempty(e.G), E);
G_max = max(arrayfun(@(e) max([e.G; 0]), E));
for i = 1:n
    fprintf('%s: R_FEEDBACK %g ohm (calibracion.csv); el firmware calculó con %.0f ohm -> G x%.3g del log; desfase %.2f s\n', ...
            nombres{i}, E(i).R_lista, E(i).R_firmware, E(i).R_firmware / E(i).R_lista, E(i).desfase);
end
salida = fullfile(E(1).raiz, 'informes', 'figuras', 'matlab_figuras');
sufijo = ['__' strjoin(nombres, '-')];
if strlength(sufijo) > 112, sufijo = sprintf('__%densayos_%s_a_%s', n, nombres{1}, nombres{end}); end
if guardar && ~isfolder(salida), mkdir(salida); end
exportar = cargar_datos('exportar');               % saves one figure in every format of "formatos"
guardar_fig = @(nombre) exportar(gcf, fullfile(salida, [nombre sufijo]), formatos, resolucion);

%% 0. R_FEEDBACK: calibracion.csv vs la que usó el firmware, en todos los registros de crudos/
t0 = tic;  fprintf('%s... ', '0. R_FEEDBACK');
% G_lista_sobre_G_firmware = by how much G changes with respect to the G the firmware logged.
% The firmware value is the constant it was programmed with: it does not measure the resistor on the board.
if ~exist('R_feedback', 'var'), R_feedback = cargar_datos('R_feedback'); end   % "clear R_feedback" to read the logs again
fprintf('%.1f s\n', toc(t0));  disp(R_feedback)

%% 1. V media vs tiempo
t0 = tic;  fprintf('%s... ', '1. V media vs tiempo');
figure('Name', 'V media vs tiempo');  hold on
for i = 1:n
    plot(E(i).t / 60, movmean(E(i).V, suav, 'omitnan', 'SamplePoints', E(i).t), 'Color', colores(i, :), 'DisplayName', nombres{i});
end
yline(umbral, '--', 'umbral', 'HandleVisibility', 'off');
xlim([0 min(duracion_min, max(vertcat(E.t)) / 60)]);
xlabel('t [min]');  ylabel('V_{media} [mm/s]');  legend;
if guardar, guardar_fig('velocidad_tiempo'); end
drawnow;  fprintf('%.1f s\n', toc(t0));

%% 2. Distribución de V media
t0 = tic;  fprintf('%s... ', '2. Distribución de V media');
% 'pdf' = density (integrates to 1); 'probability' = fraction of the frames in each bin
figure('Name', 'Distribucion de V');  hold on
bordes = linspace(0, max(vertcat(E.V)), 61);
for i = 1:n
    histogram(E(i).V, bordes, 'Normalization', 'pdf', 'DisplayStyle', 'stairs', 'LineWidth', 1.3, ...
              'EdgeColor', colores(i, :), 'DisplayName', nombres{i});
end
set(gca, 'YScale', 'log');  xlabel('V_{media} [mm/s]');  ylabel('P(V) [s/mm]');  legend;
if guardar, guardar_fig('distribucion_velocidad'); end
drawnow;  fprintf('%.1f s\n', toc(t0));

%% 3. 1 - F(V / <V>): cola de la distribución (solo la forma, sin la escala)
t0 = tic;  fprintf('%s... ', '3. 1 - F(V / <V>)');
figure('Name', '1 - F(V)');  hold on
for i = 1:n
    v = sort(rmmissing(E(i).V));
    plot(v / mean(v), (numel(v):-1:1) / numel(v), 'Color', colores(i, :), 'DisplayName', nombres{i});
end
set(gca, 'YScale', 'log');  xlabel('V / \langle V \rangle');  ylabel('P(V \geq v)');  legend;
if guardar, guardar_fig('ccdf_velocidad'); end
drawnow;  fprintf('%.1f s\n', toc(t0));

%% 4. Distribución de ω (> 0 antihorario)
t0 = tic;  fprintf('%s... ', '4. Distribución de ω');
figure('Name', 'Distribucion de omega');  hold on
for i = 1:n
    histogram(E(i).omega, -60:2:60, 'Normalization', 'pdf', 'DisplayStyle', 'stairs', 'LineWidth', 1.3, ...
              'EdgeColor', colores(i, :), 'DisplayName', nombres{i});
    fprintf('%s: ω media %.2f °/s, %.0f %% del tiempo antihorario\n', nombres{i}, mean(E(i).omega), 100 * mean(E(i).omega > 0));
end
xline(0, 'HandleVisibility', 'off');  xlabel('\omega [°/s]');  ylabel('densidad [s/°]');  legend;
if guardar, guardar_fig('distribucion_omega'); end
drawnow;  fprintf('%.1f s\n', toc(t0));

%% 5. Ocupación del recinto (robots/cm², promedio en el tiempo)
t0 = tic;  fprintf('%s... ', '5. Ocupación del recinto');
figure('Name', 'Ocupacion', 'Position', [2 2 17 11]);
tl = tiledlayout('flow', 'TileSpacing', 'compact');
b = -92.5:5:92.5;                                   % 5 mm cells over the inner diameter (185 mm)
c = (b(1:end - 1) + b(2:end)) / 2 / 10;             % cell centres [cm]
dentro = hypot(c, c') <= 9.25;                      % cells inside the wall (white outside)
todas = [];
for i = 1:n
    nexttile;
    N = histcounts2(E(i).x, E(i).y, b, b)' / E(i).nf / 0.25;     % counts / frames / 0.25 cm^2 (rows = y)
    imagesc(c, c, N, 'AlphaData', dentro);  axis xy equal tight
    rectangle('Position', [-9.25 -9.25 18.5 18.5], 'Curvature', 1, 'EdgeColor', [0.3 0.3 0.3]);
    title(nombres{i}, 'Interpreter', 'none');
    todas = [todas; N(dentro)]; %#ok<AGROW>
end
% One colour scale: 99th percentile of every cell of every trial (a few cells under robots stuck in a jam
% would otherwise push the top up and leave the other panels flat)
set(findobj(gcf, 'Type', 'axes'), 'CLim', [0 prctile(todas, 99)]);
cb = colorbar;  cb.Layout.Tile = 'east';  cb.Label.String = 'robots/cm^2';
xlabel(tl, 'x [cm]');  ylabel(tl, 'y [cm]');
if guardar, guardar_fig('ocupacion'); end
drawnow;  fprintf('%.1f s\n', toc(t0));

%% 6. G vs tiempo (eje de tiempo del video)
t0 = tic;  fprintf('%s... ', '6. G vs tiempo');
figure('Name', 'G vs tiempo');  hold on
for i = find(hay_G)
    g = movmean(E(i).G, suav, 'omitnan', 'SamplePoints', E(i).ts);
    g(isnan(E(i).G) | g < G_minimo) = NaN;          % outside the analysed spans; ADC quantisation below G_minimo
    k = 1:round(1 / E(i).paso):numel(g);            % one point per second is enough after the 30 s average
    plot((E(i).ts(k) - E(i).desfase) / 60, g(k), 'Color', colores(i, :), 'DisplayName', nombres{i});
end
set(gca, 'YScale', 'log');  xlim([0 min(duracion_min, max(vertcat(E.t)) / 60)]);  xlabel('t [min]');  ylabel('G [\muS]');  legend;
if guardar, guardar_fig('G_tiempo'); end
drawnow;  fprintf('%.1f s\n', toc(t0));

%% 7. P(G ≥ g), con G dividida por su media
t0 = tic;  fprintf('%s... ', '7. P(G ≥ g), con G dividida por su media');
figure('Name', 'Supervivencia de G');  hold on
for i = find(hay_G)
    g = sort(rmmissing(E(i).G));  p = (numel(g):-1:1)' / numel(g);
    m = numel(g);                                   % ~2000 points: evenly spread + dense in the tail (largest G)
    k = unique([round(linspace(1, m, 1000)), m + 1 - round(logspace(0, log10(m), 1000))]);
    k = k(g(k) >= G_minimo);                        % near-zero G (round-off, ~1e-14) would stretch the log axis
    plot(g(k), p(k), 'Color', colores(i, :), 'DisplayName', nombres{i});
end
set(gca, 'YScale', 'log');  xlabel('g');  ylabel('P(G \geq g)');  legend;
if guardar, guardar_fig('G_supervivencia'); end
drawnow;  fprintf('%.1f s\n', toc(t0));

%% 8. Histograma de G (clases logarítmicas)
t0 = tic;  fprintf('%s... ', '8. Histograma de G');
figure('Name', 'Histograma de G');  hold on
for i = find(hay_G)
    histogram(E(i).G, logspace(log10(G_minimo), log10(G_max), 41), 'Normalization', 'pdf', 'DisplayStyle', 'stairs', ...
              'LineWidth', 1.3, 'EdgeColor', colores(i, :), 'DisplayName', nombres{i});
end
set(gca, 'Xscale', 'log', 'YScale', 'log');  xlabel('G [\muS]');  ylabel('densidad [1/\muS]');  legend;
if guardar, guardar_fig('G_histograma'); end
drawnow;  fprintf('%.1f s\n', toc(t0));

%% 9. Asimetría de ΔG = G(t) - G(t - ΔT) en función de ΔT
t0 = tic;  fprintf('%s... ', '9. Asimetría de ΔG = G(t) - G(t - ΔT) en función de ΔT');
figure('Name', 'Asimetria de Delta G');  hold on
for i = find(hay_G)
    L = unique(round((0.05:0.05:15) / E(i).paso));          % lags in samples, 0.05 to 15 s
    s = arrayfun(@(l) skewness(rmmissing(E(i).G(l + 1:end) - E(i).G(1:end - l)), 0), L);   % 0 = bias-corrected
    plot(L * E(i).paso, s, 'Color', colores(i, :), 'DisplayName', nombres{i});
end
yline(0, 'HandleVisibility', 'off');  xlabel('\DeltaT [s]');  ylabel('asimetría de \DeltaG');  legend;
if guardar, guardar_fig('asimetria_deltaT'); end
drawnow;  fprintf('%.1f s\n', toc(t0));

%% 10. Distribución de ΔG / σ para un ΔT (colas comparadas con la normal)
t0 = tic;  fprintf('%s... ', '10. Distribución de ΔG / σ para un ΔT');
figure('Name', 'Distribucion de Delta G');  hold on
z = -10:0.25:10;
for i = find(hay_G)
    L = round(deltaT / E(i).paso);
    d = rmmissing(E(i).G(L + 1:end) - E(i).G(1:end - L));
    histogram((d - mean(d)) / std(d), z, 'Normalization', 'pdf', 'DisplayStyle', 'stairs', 'LineWidth', 1.3, ...
              'EdgeColor', colores(i, :), 'DisplayName', sprintf('%s (asimetría %.2f)', nombres{i}, skewness(d, 0)));
end
plot(z, normpdf(z), 'k--', 'DisplayName', 'normal');
set(gca, 'YScale', 'log');  xlabel(sprintf('\\DeltaG / \\sigma  (\\DeltaT = %g s)', deltaT));  ylabel('densidad');  legend;
if guardar, guardar_fig('deltaG_distribucion'); end
drawnow;  fprintf('%.1f s\n', toc(t0));

%% 11. Distribución de ΔG en µS
t0 = tic;  fprintf('%s... ', '11. Distribución de ΔG en µS');
figure('Name', 'Distribucion de Delta G sin normalizar');  hold on
D = cell(1, n);
for i = find(hay_G)
    L = round(deltaT / E(i).paso);
    D{i} = rmmissing(E(i).G(L + 1:end) - E(i).G(1:end - L));
end
lim = max(cellfun(@(d) prctile(abs([d; 0]), 99.9), D(hay_G)));   % common bins: 99.9 % of |dG| of every trial
bordes_dG = linspace(-lim, lim, 81);
for i = find(hay_G)
    histogram(D{i}, bordes_dG, 'Normalization', 'pdf', 'DisplayStyle', 'stairs', 'LineWidth', 1.3, ...
              'EdgeColor', colores(i, :), 'DisplayName', sprintf('%s (σ = %.3g µS)', nombres{i}, std(D{i})));
end
set(gca, 'YScale', 'log');  xlabel(sprintf('\\DeltaG [\\muS]  (\\DeltaT = %g s)', deltaT));  ylabel('densidad [1/\muS]');  legend;
if guardar, guardar_fig('deltaG_distribucion_uS'); end
drawnow;  fprintf('%.1f s\n', toc(t0));

%% 12. G mediana por clase de V media (ρ de Spearman)
t0 = tic;  fprintf('%s... ', '12. G mediana por clase de V media');
suav_vg = 15;                                       % smoothing of V and G for this figure [s]
figure('Name', 'G vs V media');  hold on
bordes = linspace(0, max(vertcat(E.V)), 26);
for i = find(hay_G)
    v = movmean(E(i).V, suav_vg, 'omitnan', 'SamplePoints', E(i).t);
    g = movmean(E(i).G_cuadro, suav_vg, 'omitnan', 'SamplePoints', E(i).t);
    ok = isfinite(v) & isfinite(E(i).G_cuadro) & g > G_minimo;
    v = v(ok);  g = g(ok);  k = discretize(v, bordes);  q = ~isnan(k);
    mediana = accumarray(k(q), g(q), [numel(bordes) - 1, 1], @median, NaN);
    mediana(accumarray(k(q), 1, [numel(bordes) - 1, 1]) < 30) = NaN;      % at least 30 frames (10 s) per class
    plot(bordes(1:end - 1) + diff(bordes) / 2, mediana, '-o', 'Color', colores(i, :), 'MarkerFaceColor', colores(i, :), ...
         'MarkerSize', 4, 'DisplayName', sprintf('%s (ρ = %.2f)', nombres{i}, corr(v, g, 'Type', 'Spearman')));
end
xline(umbral, '--', 'umbral', 'HandleVisibility', 'off');
set(gca, 'YScale', 'log');  xlabel('V_{media} [mm/s]');  ylabel('G [\muS]');  legend;
if guardar, guardar_fig('G_vs_velocidad'); end
drawnow;  fprintf('%.1f s\n', toc(t0));

%% 13. Histograma 2D de V media vs G (un panel por ensayo, misma escala de color)
t0 = tic;  fprintf('%s... ', '13. Histograma 2D de V media vs G');
figure('Name', 'Histograma 2D V vs G', 'Position', [2 2 17 11]);
tl = tiledlayout('flow', 'TileSpacing', 'compact');
bordes_G = logspace(log10(G_minimo), log10(G_max), 41);  bordes_V = linspace(0, max(vertcat(E.V)), 31);
for i = find(hay_G)
    nexttile;
    ok = E(i).G_cuadro >= G_minimo & isfinite(E(i).V);
    histogram2(E(i).G_cuadro(ok), E(i).V(ok), bordes_G, bordes_V, 'DisplayStyle', 'tile', 'ShowEmptyBins', 'off', ...
               'Normalization', 'probability', 'EdgeColor', 'none');
    set(gca, 'XScale', 'log', 'ColorScale', 'log');
    yline(umbral, '--', 'umbral');
    title({nombres{i}, sprintf('ρ = %.2f', corr(E(i).G_cuadro(ok), E(i).V(ok), 'Type', 'Spearman'))}, 'Interpreter', 'none');
end
h = findobj(gcf, 'Type', 'histogram2');  valores = cat(3, h.Values);
set(findobj(gcf, 'Type', 'axes'), 'CLim', [min(valores(valores > 0)) max(valores(:))]);
cb = colorbar;  cb.Layout.Tile = 'east';  cb.Label.String = 'fracción de los cuadros';
xlabel(tl, 'G [\muS]');  ylabel(tl, 'V_{media} [mm/s]');
if guardar, guardar_fig('histograma2d_V_G'); end
drawnow;  fprintf('%.1f s\n', toc(t0));
