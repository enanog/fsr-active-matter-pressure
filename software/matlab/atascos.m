%% atascos.m  -  G con los robots atascados vs en flujo libre (como Colantuono et al., PRE 2026, figs. 3 y 4)
% Cada cuadro es "atasco" si la V media suavizada (Vs) está debajo del umbral y "libre" si está arriba; los tramos
% más cortos que dur_min_estado no se usan. Cada muestra del sensor toma el estado de su cuadro.
% Dos umbrales, los dos iguales para todos los ensayos: el manual (umbral) y uno estimado con la V de todos los
% ensayos juntos. Parámetros en parametros.m. Si E ya está en el workspace (de figuras.m) no se vuelve a leer.

clc; close all;

%% Datos y clasificación
parametros;
if ~exist('E', 'var') || ~exist('E_pedido', 'var') || ~isequal(E_pedido, {ensayos, duracion_min}) || ~isfield(E, 'etiqueta')
    E = cargar_datos(ensayos, duracion_min * 60);
    E_pedido = {ensayos, duracion_min};
end
n = numel(E);  nombres = {E.codigo};  et = {E.etiqueta};
estilos = cargar_datos('estilos');  leyenda = cargar_datos('leyenda');
estados = cargar_datos('estados');  incrementos = cargar_datos('incrementos');  exportar = cargar_datos('exportar');
[colores, lineas] = estilos(E, linea_por_modo);
% G as measured, with the same floor as figuras.m (G_bajo_piso = 'cero': under G_minimo_cuentas ADC counts -> 0)
G = cell(1, n);
for i = 1:n
    if isfield(E, 'G_medido'), G{i} = E(i).G_medido; else, G{i} = E(i).G; end
    if strcmp(G_bajo_piso, 'cero'), G{i}(G{i} < G_minimo_cuentas * E(i).K) = 0; end
end
hay_G = find(~cellfun(@isempty, G));
C = estados(E, umbral, k_umbral, suav_estado, dur_min_estado);
for c = 1:2
    for i = 1:n
        fprintf('%s | umbral %s: atasco %.1f %%, libre %.1f %% del tiempo\n', nombres{i}, C(c).nombre, ...
                100 * mean(C(c).est{i} == 1), 100 * mean(C(c).est{i} == 2));
    end
end
salida = fullfile(E(1).raiz, 'informes', 'figuras', 'matlab_figuras');
if guardar && ~isfolder(salida), mkdir(salida); end
guardar_fig = @(nombre) exportar(gcf, fullfile(salida, sprintf('%s__%densayos', nombre, n)), formatos, resolucion);

%% 1. P(G ≥ g) en libre (G_b) y en atasco (G_c), y cuantiles de G_c vs G_b (paper, fig. 3b-d)
% Rows: manual / estimated threshold. Q-Q: on the dashed line both distributions are equal; above it the robots
% push harder on the wall when jammed.
p_qq = [0.5:0.5:99, 99.1:0.1:99.9];
figure('Name', 'G atasco vs libre', 'Position', [2 2 17 12]);
tl = tiledlayout(2, 3, 'TileSpacing', 'compact');  ax = gobjects(2, 3);
for c = 1:2
    for p = 1:3, ax(c, p) = nexttile(tl);  hold on; end
    tope = 0;
    for i = hay_G
        Gc = rmmissing(G{i}(C(c).est_s{i} == 1));  Gb = rmmissing(G{i}(C(c).est_s{i} == 2));
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
        fprintf('%s | %s: <G_c> = %.3g µS, <G_b> = %.3g µS (x%.2f)\n', nombres{i}, C(c).nombre, mean(Gc), mean(Gb), mean(Gc) / mean(Gb));
    end
    plot(ax(c, 3), [0 tope], [0 tope], 'k--', 'HandleVisibility', 'off');
    ylabel(ax(c, 1), {['umbral ' C(c).nombre], 'P(G \geq g)'});  ylabel(ax(c, 3), 'cuantiles de G_c [\muS]');
end
set(ax(:, 1:2), 'YScale', 'log');  linkaxes(ax(:, 1:2), 'xy');
title(ax(1, 1), 'libre (G_b)');  title(ax(1, 2), 'atasco (G_c)');  title(ax(1, 3), 'Q-Q');
xlabel(ax(2, 1), 'g [\muS]');  xlabel(ax(2, 2), 'g [\muS]');  xlabel(ax(2, 3), 'cuantiles de G_b [\muS]');
leyenda(ax(1, 3));  ax(1, 3).Legend.Layout.Tile = 'east';
if guardar, guardar_fig('atasco_G'); end

%% 2. Histograma de ΔG = G(t + ΔT) - G(t) en atasco y en libre (paper, fig. 4a-d)
% Both ends of each increment inside the same stretch. Negative asymmetry = slow build-up and sudden drops.
D = cell(2, 2, n);
for c = 1:2
    for i = hay_G
        L = round(deltaT_estado / E(i).paso);
        for s = 1:2, D{c, s, i} = incrementos(G{i}, L, C(c).est_s{i}, C(c).tramo_s{i}, s); end
    end
end
lim = prctile(abs(vertcat(D{:}, 0)), 99.9);        % common bins: 99.9 % of every |dG|
estado = {'atasco', 'libre'};
figure('Name', 'Delta G atasco vs libre', 'Position', [2 2 17 13]);
tl = tiledlayout(2, 2, 'TileSpacing', 'compact');  ax = gobjects(2, 2);
for c = 1:2
    for s = 1:2
        ax(c, s) = nexttile(tl);  hold on
        for i = hay_G
            d = D{c, s, i};
            if numel(d) < 100, continue; end
            histogram(d, linspace(-lim, lim, 81), 'Normalization', 'pdf', 'DisplayStyle', 'stairs', 'LineWidth', 1.3, ...
                      'EdgeColor', colores(i, :), 'LineStyle', lineas{i}, 'Tag', nombres{i}, ...
                      'DisplayName', sprintf('%s (asim. %.2f)', et{i}, skewness(d, 0)));
        end
        set(gca, 'YScale', 'log');  title(sprintf('%s · umbral %s', estado{s}, C(c).nombre), 'FontSize', 9);
        if ~isempty(findobj(gca, 'Type', 'histogram')), leyenda(gca);  ax(c, s).Legend.FontSize = 7; end
    end
end
linkaxes(ax, 'xy');
xlabel(tl, sprintf('\\DeltaG [\\muS]  (\\DeltaT = %g s)', deltaT_estado));  ylabel(tl, 'densidad [1/\muS]');
if guardar, guardar_fig('atasco_deltaG'); end
