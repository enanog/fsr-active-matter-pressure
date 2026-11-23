%% parametros.m  -  every setting of figuras.m and atascos.m (both scripts run it at the start)
% Change a value here and run the figure again (Ctrl+Enter on its section, or F5). Data are re-read only when
% "ensayos" or "duracion_min" change.

ensayos = {
    '20261030_1100',
    '20261030_1200',
    '20261030_1430',
    '20261030_1600',
    '20261106_1600',
    '20261112_1600',
    '20261116_1100'
};  
% ensayos           = {};           % part of the codes; {} = pick from a list
suav                = 10;           % moving average of the time plots [s]
umbral              = 0.35;         % jam threshold of V media [mm/s]: line of figures 1 and 13 (figuras.m) and manual threshold (atascos.m)
deltaT              = 2.5;          % window of dG = G(t) - G(t - deltaT) [s]
deltaT_asim         = [];           % window of figure 8b [s]; [] = the one that maximises the asymmetry of the set
rango_deltaT_asim   = [0.05 15];    % where that window is searched [s] (the asymmetry curves go from 0.05 to 15 s)
normalizar_dG_asim  = false;        % figure 8b: false = dG in uS; true = (dG - mean) / sigma (shape only)
duracion_min        = 60;           % minutes after the end of the LED (the video starts there; the sensor is cut to the same span); Inf = all
linea_por_modo      = true;         % true: line style per mode (AH -, HO -., AL --) besides the colour family; false: all solid
diametro_mm         = 33;           % robot body diameter [mm] (R = diametro_mm / 2 in E_rot)
k_inercia           = 0.5;          % moment of inertia I = k m R^2 (0.5 = uniform disc)
energia_log         = false;        % figure 4b on a log axis (jams bring E_tras down by orders of magnitude)
energia_normalizada = true;         % figure 4c: false = E in energy units; true = E / <E> of each trial (shape only)
energia_dist_juntas = false;        % figure 4c: true = translation, rotation and total on one axes; false = one panel each
G_minimo_cuentas    = 0.5;          % G floor of each trial = this many ADC counts x its K (1 count = 0.43 uS with R_FB 10 kOhm,
                                    % 0.086 uS with 50 kOhm). Below it the 50 ms mean is ADC noise/offset over 0 V (almost every
                                    % conversion is 0), not conductance: 'no contact', left out of the log axes and reported as a fraction
norm_2d             = 'total';      % figure 13 colours: 'total' = fraction of ALL the frames of the trial (one frame weighs the same in
                                    % every panel; trials with little contact look fainter); 'contacto' = fraction of the frames with contact
                                    % (shape of the distribution given contact; one frame weighs more in trials with little contact)
celdas_2d           = [25 20];      % figure 13 cells [G V]: fewer cells = more frames per cell = less Poisson noise
min_cuadros_2d      = 1;            % figure 13: cells with fewer frames than this are left empty (1 = draw every non-empty cell)
G_bajo_piso         = 'cero';       % G under the floor in the calculations: 'excluir' = left as measured (ADC noise) and out of
                                    % the log axes; 'cero' = set to 0 (removes the day-dependent noise floor from the G(t) averages
                                    % and from dG: changes the dG asymmetry with respect to 'excluir'). Never the floor value itself.
                                    % Figure 13 always shows the no-contact frames in their own column (S/C) left of the floor.

% Atasco / libre (atascos.m). Two thresholds, both the same for every trial: "umbral" (manual, above) and one
% estimated from the V of all the loaded trials together.
k_umbral            = 2;            % estimated threshold = 10^(mode - k_umbral * sigma) of log10(Vs); sigma = width above the mode
suav_estado         = 5;            % moving average of V before classifying (Vs) [s]
dur_min_estado      = 5;            % jam / free stretches shorter than this are left out [s] (the paper uses tau_th = 5 s)
deltaT_estado       = 2.5;          % window of the dG histograms of atascos.m [s]

guardar             = false;        %#ok<*UNRCH> (if guardar ... is not dead code) true: every figure -> informes/figuras/matlab_figuras/<figura>__<códigos>.<formato>
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

resolucion = 300;  % dpi of the images (.png .jpg .tif)
masa_g = 0;

% Look of every figure (MATLAB defaults for this session). Light theme even if MATLAB uses the dark one
% (R2025a+: every new figure is switched with theme(f, 'light'); older versions are always light).
if exist('theme', 'file'), set(groot, 'defaultFigureCreateFcn', @(f, ~) theme(f, 'light')); end
set(groot, 'defaultFigureColor', 'w', 'defaultFigureUnits', 'centimeters', 'defaultFigurePosition', [2 2 17 9], ...
    'defaultAxesFontSize', 10, 'defaultAxesTickDir', 'out', 'defaultAxesBox', 'off', ...
    'defaultAxesXGrid', 'on', 'defaultAxesYGrid', 'on', 'defaultLineLineWidth', 1.3, ...
    'defaultLegendBox', 'off', 'defaultLegendInterpreter', 'none', 'defaultLegendLocation', 'northeast');
% (not 'best': with hundreds of thousands of points MATLAB takes very long to place the legend)
