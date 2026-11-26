%% jamming_figures.m  -  speed, kinetic energy, occupancy, wall pressure (G), ΔG, V vs G, jams vs free flow, jam times
% Layout: TRIALS AND SHARED SETTINGS (trial sets, duration, saving, settings used by several figures) -> DATA ->
% one %% section per figure, each starting with its own settings. Ctrl+Enter runs one section, F5 runs everything.
% Data: datos/video/trayectorias/VP_<code>_conjunto.csv (per-frame group means, read first: fast),
% VP_<code>_robots.csv (per-robot positions, read only for the occupancy figure) and
% datos/presion/crudos/R_<code>.csv (FSR sensor), all through cargar_datos.m. Every trial keeps its colour in every
% figure; the colour family gives the motion mode (from the code): AH counterclockwise = blues, HO clockwise =
% greens, AL random = reds / oranges.
% Figures:
%   1  Distribution of V                       7  ΔG histogram (ΔT of maximum skewness and ΔT set by hand)
%   2  1 - F(V)                                8  2D histogram of V vs G
%   3  Kinetic energy distribution             9  P(G ≥ g) in free flow and in jams
%   4  Occupancy of the arena                 10  Quantiles of G in jams vs free flow (Q-Q)
%   5  Survival function of G                 11  P(T_c ≥ τ): jam durations (or time between jams)
%   6  Skewness of ΔG vs ΔT                   12  P(T_b ≥ τ): durations of the free stretches

clc; clear; close all;

%% ================================ TRIALS AND SHARED SETTINGS ================================
% After changing anything here: run this section and then DATA (or F5). Trials are only read again when the set,
% the duration or read_positions change.

% ---- Trial sets: each entry is part of a trial code (date_time is enough) ----
trial_sets = struct();
trial_sets.counterclockwise_22    = {'20261030_1100', '20261030_1600', '20261106_1600'};
trial_sets.random_22              = {'20261030_1200', '20261030_1430', '20261112_1600', '20261116_1100'};
trial_sets.all_since_oct30        = {'20261030_1100', '20261030_1200', '20261030_1430', '20261030_1600', '20261106_1600', ...
                                     '20261112_1600', '20261116_1100', '20261117_1300', '20261117_1600'};
trial_sets.random_removing_robots = {'20261116_1100', '20261117_1300', '20261117_1600'};    % random mode, 22 -> 20 / 21 robots
trial_sets.cc_removing_robots     = {'20261116_1100', '20261117_1300', '20261117_1600'};    % counterclockwise mode, 22 -> 20 / 21 robots

trial_set = 'all_since_oct30';   % name of one of the sets above; a cell array of codes; {} = choose from a list

% ---- General ----
duration_min        = 40;           % minutes after the end of the LED (video and sensor cut to the same span); Inf = all
read_positions      = false;        % false = only VP_<code>_conjunto.csv (fast); the per-robot positions are read when
                                    % figure 4 needs them. true = read VP_<code>_robots.csv from the start
line_per_mode       = true;        % true: line style per mode (AH -, HO -., AL --) besides the colour family

% ---- Saving (every figure) ----
save_figures        = true ;        %#ok<*UNRCH> true: every figure -> <save_folder>/<figure>__<codes>.<format>
save_folder         = 'ask';        % '' = informes/figuras/matlab_figuras (default)
                                    % relative path = from the project root, e.g. 'informes/figuras/poster'
                                    % absolute path = used as is, e.g. 'C:\Users\dylan\Desktop\figuras'
                                    % 'ask' = choose the folder in a dialog (once per run of the DATA section)
formats = {                         % one per line; % in front switches a format off
    '.png'
    % '.pdf'
    % '.svg'
    % '.fig'
};
resolution          = 300;          % dpi of the images (.png .jpg .tif)

% ---- G: no-contact floor (figures 5-10) ----
G_floor_counts      = 0.5;          % G floor of each trial = this many ADC counts x its K (below it: ADC noise, no contact)
G_below_floor       = 'zero';       % 'zero' = G under the floor set to 0; 'exclude' = left as measured and out of log axes

% ---- ΔG = G(t) - G(t - ΔT) (figures 6 and 7) ----
deltaT_search       = [0.05 15];    % range where the window of maximum skewness of the set is searched [s]
deltaT_manual       = 2.5;          % window set by hand [s]

% ---- Jam / free classification (figures 8-12) ----
% A frame is 'jam' when Vs (V smoothed over smooth_state) < u and 'free' when Vs > u.
threshold_type      = 'manual';   % 'manual' = u = threshold for every trial; 'relative' = u = threshold_rel x median V
                                    % of each trial (the free speed changes between days: with a fixed 0.35 mm/s some
                                    % trials never jam)
threshold           = 0.35;         % [mm/s] ('manual')
threshold_rel       = 0.5;          % fraction of the median V of each trial ('relative')
smooth_state        = 1;          % moving average of V before classifying [s]
min_dur_state       = 5;            % jam / free stretches shorter than this are not used in figures 9-10 [s]

% ---- Figure appearance ----
if exist('theme', 'file'), set(groot, 'defaultFigureCreateFcn', @(f, ~) theme(f, 'light')); end
set(groot, 'defaultFigureColor', 'w', 'defaultFigureUnits', 'centimeters', 'defaultFigurePosition', [2 2 17 9], ...
    'defaultAxesFontSize', 10, 'defaultAxesTickDir', 'out', 'defaultAxesBox', 'off', ...
    'defaultAxesXGrid', 'on', 'defaultAxesYGrid', 'on', 'defaultLineLineWidth', 1.3, ...
    'defaultLegendBox', 'off', 'defaultLegendInterpreter', 'none', 'defaultLegendLocation', 'northeast');

%% ============================================ DATA ============================================
% Uses: every setting of the section above.
if iscell(trial_set)
    trial_codes = trial_set;
elseif isfield(trial_sets, trial_set)
    trial_codes = trial_sets.(trial_set);
else
    error('Unknown trial set "%s". Available: %s', trial_set, strjoin(fieldnames(trial_sets), ', '));
end
request = {trial_codes, duration_min};
if ~exist('E_raw', 'var') || ~exist('E_request', 'var') || ~isequal(E_request, request) || ~isfield(E_raw, 'conjunto') ...
        || (read_positions && any(arrayfun(@(e) isempty(e.x), E_raw)))
    E_raw = cargar_datos(trial_codes, duration_min * 60, read_positions);   % group means first (VP_<code>_conjunto.csv)
    E_request = request;
end
% Trials with English field names (cargar_datos returns them in Spanish)
mode_names = struct('AH', 'Counterclockwise', 'HO', 'Clockwise', 'AL', 'Random', 'otro', 'No mode');
T = struct('code', {E_raw.codigo}, 'label', {E_raw.etiqueta}, 'mode', {E_raw.modo}, ...
           'mode_name', cellfun(@(m) mode_names.(m), {E_raw.modo}, 'UniformOutput', false), 'root', {E_raw.raiz}, ...
           't', {E_raw.t}, 'V', {E_raw.V}, 'nf', {E_raw.nf}, 'v2', {E_raw.v2}, 'w2', {E_raw.w2}, 'N', {E_raw.N}, ...
           'x', {E_raw.x}, 'y', {E_raw.y}, 'ts', {E_raw.ts}, 'G_measured', {E_raw.G}, 'G_frame_measured', {E_raw.G_cuadro}, ...
           'step', {E_raw.paso}, 'offset', {E_raw.desfase}, 'K', {E_raw.K}, 'R_list', {E_raw.R_lista});
n = numel(T);  codes = {T.code};  labels = {T.label};    % codes: files and console; labels: legends and titles
styles = cargar_datos('estilos');  legend_fn = cargar_datos('leyenda');
legend_by_mode = @(ax) legend_fn(ax, 'en');              % legend grouped by mode, English headers
[colors, line_styles, markers] = styles(struct('modo', {T.mode}), line_per_mode);
% Panels (figures 4 and 8): one row per mode, trials in date order; 'flow' if a mode has more than 4 trials
[~, ~, group] = unique({T.mode}, 'stable');  group = group(:)';
column = arrayfun(@(i) nnz(group(1:i) == group(i)), 1:n);
n_rows = max(group);  n_cols = max(column);  by_row = n_cols <= 4;
tile = (group - 1) * n_cols + column;
fprintf('Order: %s\n', strjoin(strcat({T.mode}, {': '}, codes), ' | '));
% G floor of every trial [uS] = G_floor_counts ADC counts x K (R_FEEDBACK of calibracion.csv); G_below_floor is always
% applied to the measured G, so switching it and re-running this section is enough
G_floor = G_floor_counts * [T.K];
for i = 1:n
    T(i).G = T(i).G_measured;  T(i).G_frame = T(i).G_frame_measured;
    g = T(i).G(isfinite(T(i).G));
    if isempty(g), continue; end
    fprintf('%s: G floor %.3g µS (%g counts x %.4f µS/count); %.1f %% of the samples below it (no contact)\n', ...
            codes{i}, G_floor(i), G_floor_counts, T(i).K, 100 * mean(g < G_floor(i)));
    if strcmp(G_below_floor, 'zero')                % NaN (outside the analysed spans) stays NaN
        T(i).G(T(i).G < G_floor(i)) = 0;  T(i).G_frame(T(i).G_frame < G_floor(i)) = 0;
    end
end
has_G = ~arrayfun(@(e) isempty(e.G), T);
G_max = max(arrayfun(@(e) max([e.G; 0]), T));
% Skewness of dG vs window for every trial (figures 6 and 7); only recomputed when its inputs change
asym_key = {codes, duration_min, G_below_floor, G_floor_counts};
if ~exist('asym', 'var') || ~isequal(asym.key, asym_key)
    t0 = tic;  fprintf('Skewness of ΔG vs ΔT... ');
    asym = struct('key', {asym_key}, 'dT', 0.05:0.05:15);
    asym.s = nan(n, numel(asym.dT));                % rows = trials, NaN without sensor log
    for i = find(has_G)
        lags = max(round(asym.dT / T(i).step), 1);
        asym.s(i, :) = arrayfun(@(l) skewness(rmmissing(T(i).G(l + 1:end) - T(i).G(1:end - l)), 0), lags);   % 0 = bias-corrected
    end
    fprintf('%.1f s\n', toc(t0));
end
% Window of maximum skewness of the set: maximum over dT of the mean |skewness| of the trials
asym_mean = mean(abs(asym.s(has_G, :)), 1, 'omitnan');
asym_mean(asym.dT < deltaT_search(1) | asym.dT > deltaT_search(2)) = NaN;
[asym_max, j] = max(asym_mean);  dT_max = asym.dT(j);
fprintf('ΔT of maximum skewness of the set = %.2f s (mean |skewness| = %.2f); manual ΔT = %.2f s\n', dT_max, asym_max, deltaT_manual);
% Jam threshold of every trial [mm/s] and smoothed speed Vs (figures 8-12)
Vs = arrayfun(@(e) movmean(e.V, smooth_state, 'omitnan', 'SamplePoints', e.t), T, 'UniformOutput', false);
Vs_min = cellfun(@min, Vs);
switch threshold_type
    case 'manual',   u_thr = repmat(threshold, 1, n);  threshold_text = sprintf('%.2f mm/s', threshold);
    case 'relative', u_thr = threshold_rel * arrayfun(@(e) median(e.V, 'omitnan'), T);
                     threshold_text = sprintf('%.2f × median V', threshold_rel);
    otherwise,       error('threshold_type must be ''manual'' or ''relative''.');
end
% Output folder (save_folder): default, relative to the project root, absolute, or chosen in a dialog
save_folder = strtrim(char(save_folder));
if isempty(save_folder)
    out_dir = fullfile(T(1).root, 'informes', 'figuras', 'matlab_figuras');
elseif strcmpi(save_folder, 'ask')
    out_dir = '';                                   % only asked when figures are going to be saved
    if save_figures, out_dir = uigetdir(fullfile(T(1).root, 'informes', 'figuras'), 'Folder for the figures'); end
    if isequal(out_dir, 0)                          % dialog cancelled: nothing is saved
        save_figures = false;  out_dir = '';  fprintf('No folder chosen: figures will not be saved.\n');
    end
elseif ~isempty(regexp(save_folder, '^([A-Za-z]:[\\/]|[\\/])', 'once'))   % C:\..., \\server\..., /...
    out_dir = save_folder;
else
    out_dir = fullfile(T(1).root, save_folder);
end
if save_figures, fprintf('Figures are saved in %s\n', out_dir); end
suffix = ['__' strjoin(codes, '-')];
if strlength(suffix) > 112, suffix = sprintf('__%dtrials_%s_to_%s', n, codes{1}, codes{end}); end
if save_figures && ~isfolder(out_dir), mkdir(out_dir); end
export_fn = cargar_datos('exportar');               % saves one figure in every format of "formats"
save_fig = @(name) export_fn(gcf, fullfile(out_dir, [name suffix]), formats, resolution);

%% 1. Distribution of V
% ---- settings ----
n_bins_V            = 60;           % number of bins between 0 and the largest V of all the trials
% ------------------
t0 = tic;  fprintf('%s... ', '1. Distribution of V');
figure('Name', 'Distribution of V');  hold on
edges_V1 = linspace(0, max(vertcat(T.V)), n_bins_V + 1);
for i = 1:n
    histogram(T(i).V, edges_V1, 'Normalization', 'pdf', 'DisplayStyle', 'stairs', 'LineWidth', 1.3, ...
              'EdgeColor', colors(i, :), 'LineStyle', line_styles{i}, 'Tag', codes{i}, 'DisplayName', labels{i});
end
set(gca, 'YScale', 'log');  xlabel('V_{mean} [mm/s]');  ylabel('P(V) [s/mm]');  legend_by_mode(gca);
if save_figures, save_fig('V_distribution'); end
drawnow;  fprintf('%.1f s\n', toc(t0));

%% 2. 1 - F(V): tail of the distribution of V
% ---- settings ----
normalize_V         = false;         % true = V / <V> of each trial (shape only, without the speed scale); false = V [mm/s]
% ------------------
t0 = tic;  fprintf('%s... ', '2. 1 - F(V)');
figure('Name', '1 - F(V)');  hold on
for i = 1:n
    v = sort(rmmissing(T(i).V));
    if normalize_V, v = v / mean(v); end
    plot(v, (numel(v):-1:1) / numel(v), 'Color', colors(i, :), 'LineStyle', line_styles{i}, 'Tag', codes{i}, 'DisplayName', labels{i});
end
set(gca, 'YScale', 'log');  ylabel('P(V \geq v)');  legend_by_mode(gca);
if normalize_V, xlabel('v / \langle V \rangle');  file_name = 'V_ccdf_normalized'; else, xlabel('v [mm/s]');  file_name = 'V_ccdf'; end
if save_figures, save_fig(file_name); end
drawnow;  fprintf('%.1f s\n', toc(t0));

%% 3. Distribution of the kinetic energy per frame
% ---- settings ----
diameter_mm         = 33;           % robot body diameter [mm]
k_inertia           = 0.5;          % I / m = k R^2 (0.5 = uniform disc)
normalize_energy    = false;        % true = E / <E> of each trial and component (shape only)
energy_one_axes     = false;        % true = translation, rotation and total on one axes; false = one panel each
n_bins_E            = 60;           % log bins between the 0.1 and 99.9 percentiles of all the values
% ------------------
t0 = tic;  fprintf('%s... ', '3. Kinetic energy distribution');
% Per unit mass (no robot mass in the equations), per frame, summed over the robots:
% E_tr / m = N <½ v²>, E_rot / m = N <½ k R² ω²> [mm²/s²] (König: the orbit is already in v).
% One sample per frame, no moving average; 'probability' = fraction of the frames per bin.
components = {'Translation', 'Rotation', 'Total'};  X = cell(3, n);  comp_style = {':', '--', '-'};
for i = 1:n
    E_tr = T(i).N .* T(i).v2 / 2;                                          % [mm^2/s^2]
    E_rot = T(i).N .* k_inertia * (diameter_mm / 2) ^ 2 .* T(i).w2 / 2;     % [mm^2/s^2] (w2 in rad^2/s^2)
    X(:, i) = {E_tr; E_rot; E_tr + E_rot};
    if normalize_energy, X(:, i) = cellfun(@(x) x / mean(x, 'omitnan'), X(:, i), 'UniformOutput', false); end
    q = cellfun(@(x) prctile(x, [10 50 90]), X(:, i), 'UniformOutput', false);
    fprintf('\n  %s: median [p10 p90]  translation %.3g [%.3g %.3g]  rotation %.3g [%.3g %.3g]  total %.3g [%.3g %.3g]', ...
            codes{i}, q{1}([2 1 3]), q{2}([2 1 3]), q{3}([2 1 3]));
end
all_E = vertcat(X{:});  all_E = all_E(all_E > 0 & isfinite(all_E));
edges_E = logspace(log10(prctile(all_E, 0.1)), log10(prctile(all_E, 99.9)), n_bins_E + 1);
if normalize_energy, x_label = 'E_k / \langle E_k \rangle'; else, x_label = 'E_k / m [mm^2/s^2]'; end
if energy_one_axes
    figure('Name', 'Kinetic energy distribution');  hold on
    for i = 1:n
        for p = 1:3
            x = X{p, i};
            h = histogram(x(x > 0), edges_E, 'Normalization', 'probability', 'DisplayStyle', 'stairs', 'LineWidth', 1.4, ...
                          'EdgeColor', colors(i, :), 'LineStyle', comp_style{p}, 'Tag', codes{i}, 'DisplayName', labels{i});
            if p < 3, h.HandleVisibility = 'off'; end   % one legend entry per trial
        end
    end
    for p = 1:3, plot(NaN, NaN, 'k', 'LineStyle', comp_style{p}, 'LineWidth', 1.4, 'DisplayName', components{p}); end
    set(gca, 'XScale', 'log');  xlabel(x_label);  ylabel('fraction of frames');  legend_by_mode(gca);
    file_name = 'energy_distribution_one_axes';
else
    figure('Name', 'Kinetic energy distribution', 'Position', [2 2 17 18]);
    tl = tiledlayout(3, 1, 'TileSpacing', 'compact');  ax = gobjects(1, 3);
    for p = 1:3
        ax(p) = nexttile(tl);  hold(ax(p), 'on');  title(ax(p), components{p});
        for i = 1:n
            x = X{p, i};
            histogram(ax(p), x(x > 0), edges_E, 'Normalization', 'probability', 'DisplayStyle', 'stairs', 'LineWidth', 1.3, ...
                      'EdgeColor', colors(i, :), 'LineStyle', line_styles{i}, 'Tag', codes{i}, 'DisplayName', labels{i});
        end
    end
    set(ax, 'XScale', 'log');  linkaxes(ax, 'xy');  xticklabels(ax(1:2), {});
    xlabel(tl, x_label);  ylabel(tl, 'fraction of frames');
    legend_by_mode(ax(1));  ax(1).Legend.Layout.Tile = 'east';
    file_name = 'energy_distribution';
end
if normalize_energy, file_name = [file_name '_normalized']; end
if save_figures, save_fig(file_name); end
drawnow;  fprintf('\n%.1f s\n', toc(t0));

%% 4. Occupancy of the arena (robots/cm², time average)
% ---- settings ----
cell_mm             = 2.5;          % cell size [mm]
arena_d_mm          = 185;          % inner diameter of the arena [mm]
% ------------------
% Needs the per-robot positions (VP_<code>_robots.csv): read here only if DATA did not read them.
if any(arrayfun(@(e) isempty(e.x), T))
    if ~exist('E_pos', 'var') || ~exist('E_pos_request', 'var') || ~isequal(E_pos_request, request)
        fprintf('4. Reading the per-robot positions...\n');
        E_pos = cargar_datos(trial_codes, duration_min * 60, true);
        E_pos_request = request;
    end
    for i = 1:n
        k = find(strcmp({E_pos.codigo}, T(i).code), 1);
        if ~isempty(k), T(i).x = E_pos(k).x;  T(i).y = E_pos(k).y; end
    end
end
t0 = tic;  fprintf('%s... ', '4. Occupancy');
figure('Name', 'Occupancy', 'Position', [2 2 17 11]);
if by_row, tl = tiledlayout(n_rows, n_cols, 'TileSpacing', 'compact'); else, tl = tiledlayout('flow', 'TileSpacing', 'compact'); end
R_mm = arena_d_mm / 2;
b = -R_mm:cell_mm:R_mm;                             % cell edges [mm]
c = (b(1:end - 1) + b(2:end)) / 2 / 10;             % cell centres [cm]
inside = hypot(c, c') <= R_mm / 10;
all_cells = [];
for i = 1:n
    if by_row, nexttile(tile(i)); else, nexttile; end
    if isempty(T(i).x), title({labels{i}, 'no positions'}, 'Interpreter', 'none');  axis off;  continue; end
    occ = histcounts2(T(i).x, T(i).y, b, b)' / T(i).nf / (cell_mm / 10) ^ 2;   % counts / frames / cell area (rows = y)
    imagesc(c, c, occ, 'AlphaData', inside);  axis xy equal tight
    rectangle('Position', R_mm / 10 * [-1 -1 2 2], 'Curvature', 1, 'EdgeColor', [0.3 0.3 0.3]);
    parts = strsplit(labels{i}, ' · ');             % short lines so the titles of neighbouring panels don't overlap
    title_lines = {strjoin(parts(1:min(2, end)), ' · ')};
    if numel(parts) > 2, title_lines{end + 1} = strjoin(parts(3:end), ' · '); end
    title(title_lines, 'Interpreter', 'none', 'Color', colors(i, :), 'FontSize', 9);
    all_cells = [all_cells; occ(inside)]; %#ok<AGROW>
end
set(findobj(gcf, 'Type', 'axes'), 'CLim', [0 prctile(all_cells, 99)]);   % common scale: 99th percentile of every cell
cb = colorbar;  cb.Layout.Tile = 'east';  cb.Label.String = 'robots/cm^2';
xlabel(tl, 'x [cm]');  ylabel(tl, 'y [cm]');
if save_figures, save_fig('occupancy'); end
drawnow;  fprintf('%.1f s\n', toc(t0));

%% 5. Survival function of G: P(G ≥ g)
% ---- settings ----
n_points_G          = 1500;         % points per curve (evenly spread + as many again dense in the tail)
% ------------------
% Uses: G_floor_counts, G_below_floor (shared)
t0 = tic;  fprintf('%s... ', '5. Survival function of G');
figure('Name', 'Survival function of G');  hold on
for i = find(has_G)
    g = sort(rmmissing(T(i).G));  P = (numel(g):-1:1)' / numel(g);  m = numel(g);
    k = unique([round(linspace(1, m, n_points_G)), m + 1 - round(logspace(0, log10(m), n_points_G))]);
    k = k(g(k) >= G_floor(i));                      % below the floor = no contact (P still over every sample)
    plot(g(k), P(k), 'Color', colors(i, :), 'LineStyle', line_styles{i}, 'Tag', codes{i}, 'DisplayName', labels{i});
end
set(gca, 'YScale', 'log');  xlabel('g [\muS]');  ylabel('P(G \geq g)');  legend_by_mode(gca);
if save_figures, save_fig('G_survival'); end
drawnow;  fprintf('%.1f s\n', toc(t0));

%% 6. Skewness of ΔG = G(t) - G(t - ΔT) vs ΔT
% Uses: deltaT_search, deltaT_manual (shared). The two windows of figure 7 are marked.
t0 = tic;  fprintf('%s... ', '6. Skewness of ΔG vs ΔT');
figure('Name', 'Skewness of Delta G');  hold on
for i = find(has_G)
    plot(asym.dT, asym.s(i, :), 'Color', colors(i, :), 'LineStyle', line_styles{i}, 'Tag', codes{i}, 'DisplayName', labels{i});
end
xline(dT_max, ':', sprintf('max. %.2f s', dT_max), 'HandleVisibility', 'off');
xline(deltaT_manual, '--', sprintf('manual %.2f s', deltaT_manual), 'HandleVisibility', 'off', 'LabelVerticalAlignment', 'bottom');
yline(0, 'HandleVisibility', 'off');  xlabel('\DeltaT [s]');  ylabel('skewness of \DeltaG');  legend_by_mode(gca);
if save_figures, save_fig('dG_skewness_vs_dT'); end
drawnow;  fprintf('%.1f s\n', toc(t0));

%% 7. Histogram of ΔG: ΔT of maximum skewness (top) and ΔT set by hand (bottom)
% ---- settings ----
normalize_dG        = false;        % false = dG in uS; true = (dG - mean) / sigma, with the normal curve
n_bins_dG           = 60;           % bins over ±(99.9th percentile of |dG| of every trial)
% ------------------
% Uses: deltaT_search, deltaT_manual (shared)
t0 = tic;  fprintf('%s... ', '7. Histogram of ΔG');
windows = [dT_max, deltaT_manual];
titles = {sprintf('\\DeltaT = %.2f s (maximum skewness of the set)', dT_max), sprintf('\\DeltaT = %.2f s (set by hand)', deltaT_manual)};
D = cell(2, n);  skew_dG = nan(2, n);  sigma = nan(2, n);
for p = 1:2
    for i = find(has_G)
        L = max(round(windows(p) / T(i).step), 1);
        d = rmmissing(T(i).G(L + 1:end) - T(i).G(1:end - L));
        sigma(p, i) = std(d);  skew_dG(p, i) = skewness(d, 0);   % sigma in uS also when normalised
        if normalize_dG, d = (d - mean(d)) / sigma(p, i); end
        D{p, i} = d;
    end
end
lim = max(cellfun(@(d) prctile(abs([d; 0]), 99.9), D(:, has_G)), [], 'all');
figure('Name', 'Histogram of Delta G', 'Position', [2 2 17 16]);
tl = tiledlayout(2, 1, 'TileSpacing', 'compact');  ax = gobjects(1, 2);
for p = 1:2
    ax(p) = nexttile(tl);  hold on
    for i = find(has_G)
        histogram(D{p, i}, linspace(-lim, lim, n_bins_dG + 1), 'Normalization', 'pdf', 'DisplayStyle', 'stairs', 'LineWidth', 1.3, ...
                  'EdgeColor', colors(i, :), 'LineStyle', line_styles{i}, 'Tag', codes{i}, ...
                  'DisplayName', sprintf('%s (skewness %.2f; σ = %.3g µS)', labels{i}, skew_dG(p, i), sigma(p, i)));
    end
    if normalize_dG
        z = linspace(-lim, lim, 400);
        plot(z, normpdf(z), 'k:', 'LineWidth', 1.6, 'DisplayName', 'normal');
    end
    set(gca, 'YScale', 'log');  title(titles{p}, 'FontSize', 9);  legend_by_mode(gca);  ax(p).Legend.FontSize = 8;
end
linkaxes(ax, 'xy');  xticklabels(ax(1), {});
if normalize_dG, xlabel(tl, '\DeltaG / \sigma');  ylabel(tl, 'density');
else, xlabel(tl, '\DeltaG [\muS]');  ylabel(tl, 'density [1/\muS]'); end
if save_figures, save_fig('dG_histogram'); end
drawnow;  fprintf('%.1f s\n', toc(t0));

%% 8. 2D histogram of V vs G (one panel per trial, same colour scale)
% ---- settings ----
norm_2d             = 'total';      % 'total' = fraction of all the frames; 'contact' = of the frames with contact
cells_2d            = [25 20];      % cells [G V]: fewer cells = more frames per cell = less Poisson noise
min_frames_2d       = 0;            % cells with fewer frames are left empty
% ------------------
% Uses: G_floor_counts and the jam threshold of each trial (dashed line), both shared.
% NC column (no contact, G under the floor of the trial): one cell wide, one empty cell left of the lowest floor; its
% G position is nominal. Dotted line = floor of the trial.
t0 = tic;  fprintf('%s... ', '8. 2D histogram of V vs G');
figure('Name', '2D histogram V vs G', 'Position', [2 2 17 11]);
if by_row, tl = tiledlayout(n_rows, n_cols, 'TileSpacing', 'compact'); else, tl = tiledlayout('flow', 'TileSpacing', 'compact'); end
edges_G = logspace(log10(min(G_floor(has_G))), log10(G_max), cells_2d(1) + 1);
edges_V = linspace(0, max(vertcat(T.V)), cells_2d(2) + 1);
w = log10(edges_G(2) / edges_G(1));                 % cell width [decades]
edges_X = [edges_G(1) * 10 .^ (-w * [2 1]), edges_G];   % NC column, empty gap cell, then the real cells
x_nc = sqrt(edges_X(1) * edges_X(2));
for i = find(has_G)
    if by_row, nexttile(tile(i)); else, nexttile; end
    valid = isfinite(T(i).G_frame_measured) & isfinite(T(i).V);
    contact = valid & T(i).G_frame_measured >= G_floor(i);
    nc = 1 - nnz(contact) / nnz(valid);
    C = [histcounts(T(i).V(valid & ~contact), edges_V); zeros(1, cells_2d(2)); ...
         histcounts2(T(i).G_frame_measured(contact), T(i).V(contact), edges_G, edges_V)];
    C(C < min_frames_2d) = 0;
    if strcmp(norm_2d, 'total'), C = C / nnz(valid); else, C = C / nnz(contact); C(1, :) = 0; end
    histogram2('XBinEdges', edges_X, 'YBinEdges', edges_V, 'BinCounts', C, 'DisplayStyle', 'tile', ...
               'ShowEmptyBins', 'off', 'EdgeColor', 'none');
    set(gca, 'XScale', 'log', 'ColorScale', 'log');
    xline(G_floor(i), ':', 'HandleVisibility', 'off');
    yline(u_thr(i), '--', 'threshold', 'FontSize', 8, 'LabelHorizontalAlignment', 'right', 'LabelVerticalAlignment', 'bottom');
    parts = strsplit(labels{i}, ' · ');             % short lines so the titles of neighbouring panels don't overlap
    title_lines = {strjoin(parts(1:min(2, end)), ' · ')};
    if numel(parts) > 2, title_lines{end + 1} = strjoin(parts(3:end), ' · '); end
    title([title_lines, {sprintf('no contact: %.0f %%', 100 * nc)}], 'Interpreter', 'none', 'Color', colors(i, :), 'FontSize', 9);
end
h = findobj(gcf, 'Type', 'histogram2');  bin_values = cat(3, h.Values);
dec = ceil(log10(edges_G(1))):floor(log10(edges_G(end)));
set(findobj(gcf, 'Type', 'axes'), 'CLim', [min(bin_values(bin_values > 0)) max(bin_values(:))], ...
    'XLim', edges_X([1 end]), 'XTick', [x_nc, 10 .^ dec], ...
    'XTickLabel', [{'NC'}, arrayfun(@(k) sprintf('10^{%d}', k), dec, 'UniformOutput', false)]);
cb = colorbar;  cb.Layout.Tile = 'east';
if strcmp(norm_2d, 'total'), cb.Label.String = 'fraction of all the frames'; else, cb.Label.String = 'fraction of the frames with contact'; end
xlabel(tl, sprintf('G [\\muS]   (NC = no contact: < %g ADC counts)', G_floor_counts));  ylabel(tl, 'V_{mean} [mm/s]');
if save_figures, save_fig(['hist2d_V_G_' norm_2d]); end
drawnow;  fprintf('%.1f s\n', toc(t0));

%% ======================================= JAMS VS FREE FLOW =======================================
% Every frame is 'jam' when Vs < u and 'free' when Vs > u (u of each trial, from the shared settings). Every sensor
% sample takes the state of its nearest frame (at most one frame away).

%% Jam / free classification (run before figures 9 and 10)
% Uses: the shared jam / free settings
states_fn = cargar_datos('estados');
state = struct('frames', {cell(1, n)}, 'samples', {cell(1, n)}, 'stretch', {cell(1, n)});
for i = 1:n                                         % one trial at a time, each with its own threshold
    Ci = states_fn(struct('V', T(i).V, 't', T(i).t, 'ts', T(i).ts, 'desfase', T(i).offset), ...
                   u_thr(i), 2, smooth_state, min_dur_state);   % Ci(1) = threshold u_thr(i) (2 = k of an unused estimate)
    state.frames{i} = Ci(1).est{1};  state.samples{i} = Ci(1).est_s{1};  state.stretch{i} = Ci(1).tramo_s{1};
    fprintf('%s | threshold %.3f mm/s (min Vs %.3f): jam %.1f %% (%.1f s), free %.1f %% of the time\n', codes{i}, u_thr(i), Vs_min(i), ...
            100 * mean(state.frames{i} == 1), nnz(state.frames{i} == 1) * median(diff(T(i).t)), 100 * mean(state.frames{i} == 2));
end

%% 9. P(G ≥ g) in free flow (G_b) and in jams (G_c)
% ---- settings ----
normalize_jam_G     = false;        % true = g = G / <G> of each trial (all its samples): dimensionless, like f_b and f_c in
                                    % Colantuono et al. fig. 3; false = G [uS]
min_samples_state   = 100;          % fewer sensor samples in a state (100 = 5 s) -> dotted curve, for orientation only
% ------------------
% Each panel is drawn on its own: a trial without jams still shows its free curve (the legend gives its lowest Vs).
t0 = tic;  fprintf('%s... ', '9. P(G ≥ g) free vs jam');
figure('Name', 'P(G) jam vs free', 'Position', [2 2 17 8]);
tl = tiledlayout(1, 2, 'TileSpacing', 'compact');  ax = gobjects(1, 2);
for p = 1:2, ax(p) = nexttile(tl);  hold on; end
for i = find(has_G)
    scale = 1;  if normalize_jam_G, scale = mean(rmmissing(T(i).G)); end   % <G> of the whole trial
    F = {rmmissing(T(i).G(state.samples{i} == 2)), rmmissing(T(i).G(state.samples{i} == 1))};   % free, jam
    t_jam = numel(F{2}) * T(i).step;                % time in jam with sensor data [s]
    for p = 1:2
        g = sort(F{p}) / scale;  P = (numel(g):-1:1)' / numel(g);
        style = {'LineStyle', line_styles{i}, 'LineWidth', 1.3};
        if ~isempty(g) && numel(g) < min_samples_state, style = {'LineStyle', ':', 'LineWidth', 1, 'Marker', '.'}; end
        if isempty(g), g = NaN;  P = NaN; end
        txt = labels{i};
        if p == 2                                   % the legend is in the jam panel
            if isnan(g(1)), txt = sprintf('%s (u = %.2f mm/s; no jam: min Vs %.2f mm/s)', labels{i}, u_thr(i), Vs_min(i));
            elseif numel(g) < min_samples_state, txt = sprintf('%s (u = %.2f mm/s; jam only %.1f s: dotted)', labels{i}, u_thr(i), t_jam);
            else, txt = sprintf('%s (u = %.2f mm/s; jam %.0f s)', labels{i}, u_thr(i), t_jam); end
        end
        plot(ax(p), g, P, 'Color', colors(i, :), style{:}, 'Tag', codes{i}, 'DisplayName', txt);
    end
    if isempty(F{1}) || isempty(F{2})
        fprintf('\n  %s: %.1f s in jam and %.1f s free', codes{i}, t_jam, numel(F{1}) * T(i).step);
    else
        fprintf('\n  %s: <G_c> = %.3g µS, <G_b> = %.3g µS (x%.2f)', codes{i}, mean(F{2}), mean(F{1}), mean(F{2}) / mean(F{1}));
    end
end
set(ax, 'YScale', 'log');  linkaxes(ax, 'xy');
title(ax(1), 'free (g_b)');  title(ax(2), 'jam (g_c)');
if normalize_jam_G, xlabel(tl, 'g = G / \langle G \rangle'); else, xlabel(tl, 'g [\muS]'); end
ylabel(ax(1), 'P(G \geq g)');
title(tl, sprintf('threshold %s', threshold_text), 'FontSize', 10);
legend_by_mode(ax(2));
if save_figures, save_fig('jam_G_survival'); end
drawnow;  fprintf('\n%.1f s\n', toc(t0));

%% 10. Quantiles of G in jams vs free flow (Q-Q)
% ---- settings ----
normalize_qq        = true;         % true = g = G / <G> of each trial (same factor on both axes: the identity line does
                                    % not change, only the overall G level of each day is removed); false = G [uS]
min_samples_qq      = 100;          % fewer jam or free samples -> dotted curve (its high quantiles come from few samples)
% ------------------
% Every point = the same percentile of G_b (x) and G_c (y), as in Colantuono et al. fig. 3d. On the dashed line both
% distributions are equal; above it the wall takes more force while the robots are jammed. Without jams the trial
% stays in the legend only.
t0 = tic;  fprintf('%s... ', '10. Q-Q of G jam vs free');
p_qq = [0.5:0.5:99, 99.1:0.1:99.9];
figure('Name', 'Q-Q G jam vs free', 'Position', [2 2 11 10]);  hold on
top = 0;
for i = find(has_G)
    Gc = rmmissing(T(i).G(state.samples{i} == 1));  Gb = rmmissing(T(i).G(state.samples{i} == 2));
    if numel(Gc) < 2 || numel(Gb) < 2               % no quantiles: legend entry only
        plot(NaN, NaN, 'Color', colors(i, :), 'LineStyle', line_styles{i}, 'Tag', codes{i}, ...
             'DisplayName', sprintf('%s (no jam: min Vs %.2f mm/s > u = %.2f)', labels{i}, Vs_min(i), u_thr(i)));
        continue
    end
    scale = 1;  if normalize_qq, scale = mean(rmmissing(T(i).G)); end   % <G> of the whole trial
    qb = prctile(Gb, p_qq) / scale;  qc = prctile(Gc, p_qq) / scale;
    style = {'LineStyle', line_styles{i}, 'LineWidth', 1.3};  txt = labels{i};
    if numel(Gc) < min_samples_qq || numel(Gb) < min_samples_qq
        style = {'LineStyle', ':', 'LineWidth', 1, 'Marker', '.'};
        txt = sprintf('%s (jam only %.1f s: dotted)', labels{i}, numel(Gc) * T(i).step);
    end
    plot(qb, qc, 'Color', colors(i, :), style{:}, 'Tag', codes{i}, 'DisplayName', txt);
    top = max([top, qb, qc]);
end
plot([0 max(top, 1)], [0 max(top, 1)], 'k--', 'HandleVisibility', 'off');
if normalize_qq, xlabel('g_b quantiles (free)');  ylabel('g_c quantiles (jam)');
else, xlabel('g_b quantiles (free) [\muS]');  ylabel('g_c quantiles (jam) [\muS]'); end
xlim([0 inf]);  ylim([0 inf]);  pbaspect([1 1 1]);
title(sprintf('threshold %s', threshold_text), 'FontSize', 10);  legend_by_mode(gca);
if save_figures, save_fig('jam_G_quantiles'); end
drawnow;  fprintf('%.1f s\n', toc(t0));

%% =================================== JAM AND FREE-FLOW TIMES ===================================
% Adapted from Colantuono et al. figs. 1c-d. There Δt is the time between two exits: Δt > τ_th is a clog and a burst is
% a run of exits with Δt < τ_th. Here there are no exits: the state comes from Vs and the threshold of each trial.
% T_c = duration of every jam (≥ tau_th); T_b = duration of every free stretch between two jams (jams < tau_th stay
% inside the free stretch). Durations come from the frame times (a video gap cuts the stretch).

%% Times: computation (run before figures 11 and 12)
% ---- settings ----
tau_th              = 5;            % [s] a jam shorter than this is not a jam (the paper's threshold between bursting and
                                    % clogging); Vs is smoothed over smooth_state, so shorter jams are not resolved anyway
free_min_s          = 0;            % [s] free stretches shorter than this between two jams are joined to the jam (0 = off)
include_edges       = false;        % false = stretches cut by the start / end of the record or by a video gap are left out
% ------------------
% Tc = complete jams ≥ tau_th; Tall = every complete slow episode, also the ones < tau_th; Tb = complete free stretches
% between two jams; Tb_cut = free stretches cut by the start, the end or a gap; Ti = time between the starts of jams.
Tc = cell(1, n);  Tb = cell(1, n);  Ti = cell(1, n);  Tall = cell(1, n);  Tb_cut = cell(1, n);
for i = 1:n
    t = T(i).t(:);  dtc = median(diff(t));  vs = Vs{i}(:);
    st = 1 * (vs < u_thr(i)) + 2 * (vs >= u_thr(i));  st(~isfinite(vs)) = 0;   % 1 jam, 2 free, 0 not usable
    gap = [false; diff(t) > 2 * dtc];               % true = first frame after a video gap
    for pass = 1:2                                  % 1: short free between two jams -> jam; 2: short jam -> free
        new = [true; diff(st) ~= 0 | gap(2:end)];
        first = find(new);  last = [first(2:end) - 1; numel(st)];
        dur = t(last) - t(first) + dtc;  s = st(first);
        before = [0; s(1:end - 1)];  after = [s(2:end); 0];
        joined_prev = ~gap(first);  joined_next = [~gap(last(1:end - 1) + 1); false];   % neighbour not across a gap
        if pass == 1
            change = s == 2 & dur < free_min_s & before == 1 & after == 1 & joined_prev & joined_next;  new_state = 1;
        else                                        % state after pass 1: every complete slow episode, short ones too
            Tall{i} = dur(s == 1 & (include_edges | (joined_prev & before ~= 0 & joined_next & after ~= 0)));
            change = s == 1 & dur < tau_th;  new_state = 2;
        end
        for k = find(change)', st(first(k):last(k)) = new_state; end
    end
    new = [true; diff(st) ~= 0 | gap(2:end)];
    first = find(new);  last = [first(2:end) - 1; numel(st)];
    dur = t(last) - t(first) + dtc;  s = st(first);
    before = [0; s(1:end - 1)];  after = [s(2:end); 0];
    % Censored stretch: starts at the record start, after a gap or after unusable frames, or ends likewise
    start_seen = ~gap(first) & before ~= 0;
    end_seen = [~gap(last(1:end - 1) + 1); false] & after ~= 0;
    use = include_edges | (start_seen & end_seen);
    Tc{i} = dur(s == 1 & use);  Tb{i} = dur(s == 2 & use);  Tb_cut{i} = dur(s == 2 & ~(start_seen & end_seen));
    kj = find(s == 1);                              % time between the starts of two consecutive jams
    Ti{i} = [];
    for a = 1:numel(kj) - 1
        if ~include_edges && ~(start_seen(kj(a)) && start_seen(kj(a + 1))), continue; end
        if any(gap(first(kj(a)) + 1:first(kj(a + 1)))), continue; end
        Ti{i}(end + 1, 1) = t(first(kj(a + 1))) - t(first(kj(a)));
    end
    fprintf('%s: %d slow episodes (%d ≥ %g s; %.1f %% of the time in jam; mean T_c %.1f s, max. %.1f s), %d free stretches (mean T_b %.1f s), %d intervals between jams\n', ...
            codes{i}, numel(Tall{i}), numel(Tc{i}), tau_th, 100 * mean(st == 1), mean(Tc{i}), max([Tc{i}; NaN]), numel(Tb{i}), mean(Tb{i}), numel(Ti{i}));
end

%% 11. P(T_c ≥ τ): jam durations (or time between jams), log-log axes
% ---- settings ----
tc_type             = 'duration';   % 'duration' = T_c, length of every jam; 'between_jams' = from the start of one jam to
                                    % the start of the next
show_short          = true;         % ('duration') also the slow episodes shorter than tau_th (hollow markers, left of the
                                    % red line), like the bursting part of the paper's fig. 1c; gamma still from τ ≥ tau_th
% ------------------
% As in the paper: PDF ∝ τ^-γ ⇒ P(T ≥ τ) ∝ τ^-(γ-1). Black line: γ = 2. γ > 2 (falls faster than the line): finite mean
% duration, unclogged; γ ≤ 2: the mean diverges, clogged. γ by maximum likelihood (continuous Pareto, τ ≥ tau_th):
% γ = 1 + n / Σ ln(τ_i / tau_th), error ≈ (γ - 1) / √n; not reliable with n of 2-4. P is computed over every plotted
% episode. A trial with nothing to plot gets a plain line in the legend ("no jams") and a line in a note box in the
% lower-left corner, in its own color.
t0 = tic;  fprintf('%s... ', '11. Survival of T_c');
if strcmp(tc_type, 'between_jams')
    Tfit = Ti;  Tplot = Ti;  symbol = '\Deltat_{c}';  fig_title = 'time between the starts of jams';
else
    Tfit = Tc;  Tplot = Tc;  symbol = 'T_c';  fig_title = 'jam durations';
    if show_short, Tplot = Tall;  fig_title = 'durations of the slow episodes (jams: \tau \geq \tau_{th})'; end
end
figure('Name', 'Survival: jams');  hold on
t_lo = tau_th;  t_hi = tau_th;  P_th = 0;  notes = {};
for i = 1:n
    x = sort(Tplot{i});  c = colors(i, :);
    if isempty(x)                                   % nothing to plot: plain legend line + note box
        if strcmp(tc_type, 'between_jams'), reason = sprintf('fewer than 2 consecutive jams ≥ %g s', tau_th);
        elseif isempty(Tall{i}), reason = sprintf('no jams (speed never below u = %.2f mm/s)', u_thr(i));
        else, reason = sprintf('no jams ≥ %g s', tau_th); end
        plot(NaN, NaN, 'Color', c, 'LineStyle', '-', 'LineWidth', 2, 'Tag', codes{i}, 'DisplayName', sprintf('%s: %s', labels{i}, reason));
        notes{end + 1} = sprintf('\\color[rgb]{%.3f,%.3f,%.3f}%s: %s', c, labels{i}, reason);
        fprintf('\n  %s: no data', codes{i});  continue
    end
    P = (numel(x):-1:1)' / numel(x);  long = x >= tau_th;
    tail = Tfit{i};  tail = tail(tail >= tau_th);  gam = NaN;
    if numel(tail) >= 2, gam = 1 + numel(tail) / sum(log(tail / tau_th)); end
    if numel(tail) >= 2, txt = sprintf('%s (u = %.2f mm/s; γ = %.2f; n = %d', labels{i}, u_thr(i), gam, numel(tail));
    else, txt = sprintf('%s (u = %.2f mm/s; n = %d ≥ τ_th: no γ', labels{i}, u_thr(i), numel(tail)); end
    if any(~long), txt = sprintf('%s; %d short)', txt, nnz(~long)); else, txt = [txt ')']; end
    plot(x, P, 'Color', c, 'LineStyle', line_styles{i}, 'LineWidth', 1, 'Tag', codes{i}, 'DisplayName', txt);
    plot(x(long), P(long), 'LineStyle', 'none', 'Marker', markers{i}, 'MarkerSize', 5, 'Color', c, 'MarkerFaceColor', c, 'HandleVisibility', 'off');
    plot(x(~long), P(~long), 'LineStyle', 'none', 'Marker', markers{i}, 'MarkerSize', 5, 'Color', c, 'MarkerFaceColor', 'w', 'HandleVisibility', 'off');
    t_lo = min(t_lo, x(1));  t_hi = max(t_hi, x(end));
    if any(long), P_th = max(P_th, P(find(long, 1))); end
    fprintf('\n  %s: %d episodes, %d ≥ %g s, γ = %.2f ± %.2f', codes{i}, numel(x), numel(tail), tau_th, gam, (gam - 1) / sqrt(numel(tail)));
end
if P_th == 0, P_th = 1; end                         % the reference line starts at the highest P(T ≥ tau_th)
tau = logspace(log10(tau_th), log10(max(t_hi, 2 * tau_th)), 50);
plot(tau, P_th * tau_th ./ tau, 'k-', 'LineWidth', 1.6, 'DisplayName', 'τ⁻¹ (γ = 2)');
xline(tau_th, 'r:', sprintf('\\tau_{th} = %g s', tau_th), 'LineWidth', 1.3, 'HandleVisibility', 'off', ...
      'LabelOrientation', 'horizontal', 'LabelVerticalAlignment', 'bottom');
set(gca, 'YScale', 'log');  xlim([t_lo / 1.2, max(t_hi, 2 * tau_th) * 1.2]);
if ~isempty(notes)                                  % lower-left corner is empty in a survival plot
    text(0.02, 0.04, notes, 'Units', 'normalized', 'HorizontalAlignment', 'left', 'VerticalAlignment', 'bottom', ...
         'Interpreter', 'tex', 'FontSize', 9, 'BackgroundColor', 'w', 'EdgeColor', [0.6 0.6 0.6], 'Margin', 4);
end
xlabel('\tau [s]');  ylabel(sprintf('P(%s \\geq \\tau)', symbol));  title(fig_title, 'FontSize', 10);  legend_by_mode(gca);
if save_figures, save_fig(['jam_times_' tc_type]); end
drawnow;  fprintf('\n%.1f s\n', toc(t0));

%% 12. P(T_b ≥ τ): durations of the free stretches, log y axis
% ---- settings ----
fit_exp             = true;         % dotted exponential exp(-τ / <T_b>) of every trial
% ------------------
% A straight line here = exponential distribution = jamming has no memory (constant probability of jamming in the
% next second). Steeper = the system jams again sooner. A trial without complete free stretches (fewer than two jams)
% has no curve: a plain line in the legend and a line in a note box on the right, in its own color, with its longest
% free stretch (cut by the start, the end or a gap: the real T_b is at least that long).
t0 = tic;  fprintf('%s... ', '12. Survival of T_b');
figure('Name', 'Survival: free stretches');  hold on
notes = {};
for i = 1:n
    x = sort(Tb{i});  c = colors(i, :);
    if isempty(x)                                   % nothing to plot: plain legend line + note box
        if isempty(Tb_cut{i}), reason = 'no free stretches';
        else, reason = sprintf('no jams, free during the whole trial (%.0f s)', max(Tb_cut{i})); end
        plot(NaN, NaN, 'Color', c, 'LineStyle', '-', 'LineWidth', 2, 'Tag', codes{i}, 'DisplayName', sprintf('%s: %s', labels{i}, reason));
        notes{end + 1} = sprintf('\\color[rgb]{%.3f,%.3f,%.3f}%s: %s', c, labels{i}, reason);
        fprintf('\n  %s: no complete free stretches; longest cut stretch %.0f s', codes{i}, max([Tb_cut{i}; NaN]));  continue
    end
    plot(x, (numel(x):-1:1)' / numel(x), 'Color', c, 'LineStyle', line_styles{i}, 'Marker', markers{i}, ...
         'MarkerSize', 4, 'MarkerFaceColor', c, 'Tag', codes{i}, ...
         'DisplayName', sprintf('%s (⟨T_b⟩ = %.1f s; n = %d)', labels{i}, mean(x), numel(x)));
    if fit_exp
        tau = linspace(0, x(end), 100);
        plot(tau, exp(-tau / mean(x)), ':', 'Color', c, 'LineWidth', 1, 'HandleVisibility', 'off');
    end
end
set(gca, 'YScale', 'log');  xlim([0 inf]);
if ~isempty(notes)                                  % right half is empty: the curves fall towards the lower left
    text(0.98, 0.5, notes, 'Units', 'normalized', 'HorizontalAlignment', 'right', 'VerticalAlignment', 'middle', ...
         'Interpreter', 'tex', 'FontSize', 9, 'BackgroundColor', 'w', 'EdgeColor', [0.6 0.6 0.6], 'Margin', 4);
end
xlabel('\tau [s]');  ylabel('P(T_b \geq \tau)');  title('durations of the free stretches', 'FontSize', 10);  legend_by_mode(gca);
if save_figures, save_fig('free_times'); end
drawnow;  fprintf('\n%.1f s\n', toc(t0));
