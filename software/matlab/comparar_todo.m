%% comparar_todo.m  -  las figuras principales de cada tema, con UNA sola elección de ensayos
% Runs the key comparison figures (velocity, rotation, collective motion, pressure, velocity vs
% pressure, summary) on the same trials. Every figure keeps the SETTINGS of its own script in
% figuras/ (colors, smoothing, limits, size...): only the trials are imposed from here.
% Edit SETTINGS and run (F5).
clear; addpath(fullfile(fileparts(mfilename('fullpath')), 'funciones'));

%% ============================ SETTINGS ============================
ensayos = {};            % {} = pick from a list of every trial (funciones/ensayos_base.m preselected) | 'todos' | {'...'} part of the code
cerrar_previas = true;   % close the figures already open
agrupar  = true;         % dock all figures as tabs of one window (after saving; MATLAB only)
guardar  = false;        % true: save every figure to informes/figuras/matlab/comparacion_<AAAAMMDD_HHMM>/
formatos = {'pdf', 'png'};
por_ensayo_VG = false;   % also fig_velocidad_y_presion (V and G vs t), one figure per trial

figuras = {              % script                     run?     what it compares
    % --- velocity
    'fig_velocidad_tiempo'        true     % V media (t): evolution and jams
    'fig_ccdf_velocidad'          true     % 1 - F(v): tails of the speed distribution
    'fig_pdf_velocidad'           true
    'fig_histograma_velocidad'    true
    'fig_energia_tiempo'          false
    % --- rotation
    'fig_omega_distribucion'      true     % distribution of omega (sign = sense of rotation)
    'fig_giro_robots'             false     % mean omega of every robot, sorted
    'fig_rotacion_tiempo'         false
    % --- collective motion and structure
    'fig_circulacion_tiempo'      false     % collective circulation Phi(t)
    'fig_msd'                     false     % mean squared displacement, exponent alpha
    'fig_densidad_radial'         false     % radial density: layers, wall, jam vs flow
    'fig_ocupacion'               true
    % --- pressure
    'fig_presion_tiempo'          true     % G(t)
    'fig_presion_supervivencia'   true     % P(G >= g)
    'fig_asimetria_deltaT'        true     % skewness of dG vs dT (poster)
    'fig_deltaG_distribucion'     true    % shape of dG (tails), normalised by sigma
    'fig_presion_histograma'      true
    'fig_deltaG_tiempo'           false
    'fig_presion_vs_robots'       false
    % --- velocity vs pressure
    'fig_presion_vs_velocidad'    true     % median G per class of V media, Spearman rho
    'fig_hexbin_velocidad_presion' false   % density of (G, V media) per frame, hexagonal bins
    % --- summary
    'fig_barras_resumen'          false     % one summary field per trial
    'fig_comparar_modos'          false     % AH vs AL
    'tabla_resumen'               false     % table in the console
    'tabla_presion'               false
};
%% ==================================================================

carpeta_scripts = fullfile(fileparts(mfilename('fullpath')), 'figuras');
codigos = elegir_codigos(buscar_ensayos(), ensayos, 'Ensayos a comparar:');
fprintf('Ensayos (%d): %s\n', numel(codigos), strjoin(codigos, ', '));
if cerrar_previas, close all; end
if guardar
    carpeta_salida = fullfile(raiz_proyecto(), 'informes', 'figuras', 'matlab', ...
                              ['comparacion_' datestr(now, 'yyyymmdd_HHMM')]);
end

tareas = figuras([figuras{:, 2}], 1);              % {script, trials, output name}
tareas(:, 2) = {codigos};
tareas(:, 3) = regexprep(tareas(:, 1), '^fig_', '');
if por_ensayo_VG
    for i = 1:numel(codigos)
        tareas(end + 1, :) = {'fig_velocidad_y_presion', codigos(i), ['velocidad_y_presion_' codigos{i}]}; %#ok<SAGROW>
    end
end

t0 = tic;  todas = [];  fallas = cell(0, 2);
for k = 1:size(tareas, 1)
    fprintf('\n=== [%d/%d] %s ===\n', k, size(tareas, 1), tareas{k, 3});
    try
        figs = correr_figura(fullfile(carpeta_scripts, [tareas{k, 1} '.m']), tareas{k, 2});
    catch err
        fallas(end + 1, :) = {tareas{k, 3}, err.message}; %#ok<SAGROW>
        fprintf(2, 'Falló %s: %s\n', tareas{k, 3}, err.message);
        continue
    end
    todas = [todas; figs(:)]; %#ok<AGROW>
    for j = 1:numel(figs) * guardar
        nombre = tareas{k, 3};
        if numel(figs) > 1, nombre = sprintf('%s_%d', nombre, j); end
        try
            guardar_figura(figs(j), fullfile(carpeta_salida, nombre), formatos);
        catch err
            fallas(end + 1, :) = {[nombre ' (guardar)'], err.message}; %#ok<SAGROW>
            fprintf(2, 'No se pudo guardar %s: %s\n', nombre, err.message);
        end
    end
end

if agrupar                                         % docked after saving: export keeps the size in cm
    for j = 1:numel(todas)
        try, set(todas(j), 'WindowStyle', 'docked'); catch, end
    end
end
fprintf('\n%d figuras en %.0f s', numel(todas), toc(t0));
if guardar, fprintf(' -> %s', carpeta_salida); end
fprintf('\n');
if ~isempty(fallas)
    fprintf(2, '\nFallaron %d:\n', size(fallas, 1));
    for k = 1:size(fallas, 1), fprintf(2, '  %s: %s\n', fallas{k, :}); end
end
