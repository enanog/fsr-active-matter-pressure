%% tabla_resumen.m  -  tabla con los valores medios de cada ensayo (en la consola y en CSV)
% Edit the SETTINGS block and run (F5).
clear; addpath(fullfile(fileparts(mfilename('fullpath')), '..', 'funciones'));

%% ============================ SETTINGS ============================
ensayos  = 'todos';        % 'todos' | {'20260924', ...} part of the code | {} = pick from a list
umbral   = 0.35;           % jam threshold [mm/s]
suavizado_s = 30;          % smoothing for rho(V, G) [s]
masa_g   = 0;              % robot mass [g]; 0 = energies per unit mass [uJ/kg]
columnas = {'V_media', 'v_mediana_indiv', 'omega_media_signo', 'robots_antihorario', 'robots_horario', ...
            'Phi_circulacion', 'pared_pct', 'alfa_msd', 'atasco_pct', 'atasco_max_s', ...
            'E_rot_sobre_E_tras', 'G_mediana_fluido', 'G_mediana_atasco', 'asim_dG', 'rho_V_G'};   % see resumen_ensayo.m
guardar_csv = false;  archivo = 'resumen_ensayos_matlab.csv';   % -> informes/figuras/matlab/
%% ==================================================================

D = cargar_ensayos(ensayos);
filas = cell(numel(D), 1);
for i = 1:numel(D)
    filas{i} = resumen_ensayo(D(i), umbral, suavizado_s, masa_g);
end
ancho = max(12, cellfun(@numel, columnas) + 2);
fprintf('\n%-22s', 'ensayo');
for c = 1:numel(columnas), fprintf('%*s', ancho(c), columnas{c}); end
fprintf('\n');
for i = 1:numel(D)
    fprintf('%-22s', filas{i}.ensayo);
    for c = 1:numel(columnas)
        fprintf('%*.4g', ancho(c), filas{i}.(columnas{c}));
    end
    fprintf('\n');
end
if guardar_csv
    carpeta = fullfile(raiz_proyecto(), 'informes', 'figuras', 'matlab');
    if ~isfolder(carpeta), mkdir(carpeta); end
    f = fopen(fullfile(carpeta, archivo), 'w');
    fprintf(f, 'codigo,ensayo,modo,%s\n', strjoin(columnas, ','));
    for i = 1:numel(D)
        fprintf(f, '%s,%s,%s', D(i).codigo, filas{i}.ensayo, filas{i}.modo);
        fprintf(f, ',%.6g', cellfun(@(c) filas{i}.(c), columnas));
        fprintf(f, '\n');
    end
    fclose(f);
    fprintf('Guardada: %s\n', fullfile(carpeta, archivo));
end
