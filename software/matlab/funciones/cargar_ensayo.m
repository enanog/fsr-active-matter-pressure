function D = cargar_ensayo(codigo)
% CARGAR_ENSAYO  One trial reduced to per-frame series (what every plot uses).
%   D.codigo, D.etiqueta, D.modo ('AH', 'HO', 'AL'), D.N (robots)
%   D.t      video time of each frame [s] (column)
%   D.V      mean speed of the group per frame, mean of |v| over the robots [mm/s]
%   D.W      <|omega|> per frame [deg/s]
%   D.V2     <v^2> per frame [mm^2/s^2]      (for the energy)
%   D.W2     <omega^2> per frame [rad^2/s^2]
%   D.v_ind  |v| of every observed robot and frame (detected or manual, no interpolated) [mm/s]
%   D.P      pressure on the sensor grid (see leer_presion); [] if there is no log
%   Per robot (frames x robots; same frame order as D.t):
%   D.X, D.Y   centre position [mm], origin at the centre of the enclosure, y away from the observer
%   D.VX, D.VY velocity [mm/s];  D.S speed |v| [mm/s];  D.Wr omega [deg/s] (> 0 counter-clockwise)
%   D.TH       accumulated orientation theta [deg];  D.OBS true where the robot was observed (not interpolated)
% The first call reads the CSV files (slow) and keeps a copy in software/matlab/cache/<code>.mat;
% later calls use it while the source files are unchanged.
    raiz = raiz_proyecto();
    fuentes = archivos_fuente(raiz, codigo);
    cache = fullfile(fileparts(fileparts(mfilename('fullpath'))), 'cache', [codigo '.mat']);
    firma = [firma_archivos(fuentes); r_feedback_lista(raiz, codigo), 0];  % + its row of calibracion.csv
    firma(isnan(firma)) = -1;
    if isfile(cache)
        S = load(cache);
        if isfield(S, 'firma') && isequal(S.firma, firma) && isfield(S, 'version') && S.version == 4
            D = S.D;
            D.etiqueta = etiqueta_ensayo(codigo);   % label rules may change after the cache was written
            return
        end
    end
    fprintf('Leyendo %s (la próxima vez sale de la caché)...\n', codigo);
    D = leer_ensayo(raiz, codigo, fuentes);
    if ~isfolder(fileparts(cache)), mkdir(fileparts(cache)); end
    version = 4; %#ok<NASGU>
    save(cache, 'D', 'firma', 'version', '-v7');
end

function f = archivos_fuente(raiz, codigo)
    tr = fullfile(raiz, 'datos', 'video', 'trayectorias');
    f = {};
    unico = fullfile(tr, ['VP_' codigo '_robots.csv']);
    if isfile(unico)
        f{1} = unico;
    else
        k = 1;
        while isfile(fullfile(tr, sprintf('VP_%s(%d)_robots.csv', codigo, k)))
            f{end+1} = fullfile(tr, sprintf('VP_%s(%d)_robots.csv', codigo, k)); %#ok<AGROW>
            k = k + 1;
        end
    end
    if isempty(f), error('No hay trayectorias de %s.', codigo); end
    extra = {fullfile(raiz, 'datos', 'presion', 'crudos', ['R_' codigo '.csv']), ...
             fullfile(raiz, 'datos', 'presion', 'config', [codigo '.json']), ...
             fullfile(raiz, 'datos', 'video', 'cortes.json')};
    f = [f, extra];
end

function s = firma_archivos(f)
    s = zeros(numel(f), 2);
    for i = 1:numel(f)
        d = dir(f{i});
        if ~isempty(d), s(i, :) = [d.datenum, d.bytes]; end
    end
end

function D = leer_ensayo(raiz, codigo, fuentes)
    partes = fuentes(~cellfun(@isempty, strfind(fuentes, [filesep 'VP_'])));
    num = {'frame', 't_s', 'particle', 'x_mm', 'y_mm', 'vx_mm_s', 'vy_mm_s', 'speed_mm_s', ...
           'omega_rad_s', 'omega_deg_s', 'theta_deg'};
    M = struct('t', [], 'X', [], 'Y', [], 'VX', [], 'VY', [], 'S', [], 'Wr', [], 'TH', [], 'OBS', []);
    for j = 1:numel(partes)
        fprintf('  %s\n', partes{j});
        T = leer_csv(partes{j}, num, {'status'});
        if all(isnan(T.omega_deg_s)), T.omega_deg_s = T.omega_rad_s * 180 / pi; end
        [Pj, tj] = a_matrices(T);
        if j > 1                                    % next part of a split recording
            hueco = hueco_corte(raiz, codigo, j - 1);
            tj = tj + M.t(end) + hueco;
            orden = emparejar([M.X(end, :); M.Y(end, :)], [Pj.X(1, :); Pj.Y(1, :)]);
            for c = fieldnames(Pj)'
                Pj.(c{1}) = Pj.(c{1})(:, orden);
            end
            Pj.TH = Pj.TH - Pj.TH(1, :) + M.TH(end, :);   % theta continues from the last value
            fprintf('  parte %d unida con un hueco de %.1f s\n', j, hueco);
        end
        M.t = [M.t; tj];
        for c = fieldnames(Pj)'
            M.(c{1}) = [M.(c{1}); Pj.(c{1})];
        end
    end
    D.codigo = codigo;
    D.etiqueta = etiqueta_ensayo(codigo);
    p = strsplit(codigo, '_');
    D.modo = regexprep(p{3}, '^\d+', '');
    M.OBS = logical(M.OBS);                         % [] + logical concatenates to double in Octave
    D.N = size(M.X, 2);
    D.t = M.t;
    D.V = mean_nan(M.S);
    D.W = mean_nan(abs(M.Wr));
    D.V2 = mean_nan(M.S .^ 2);
    D.W2 = mean_nan((M.Wr * pi / 180) .^ 2);
    v = M.S(M.OBS);
    D.v_ind = v(isfinite(v));
    for c = {'X', 'Y', 'VX', 'VY', 'S', 'Wr', 'TH', 'OBS'}
        D.(c{1}) = M.(c{1});
    end
    D.P = leer_presion(raiz, codigo);
end

function [P, t] = a_matrices(T)
    % Long table (one row per robot and frame) -> frames x robots matrices
    [fr, ~, ifr] = unique(T.frame);
    [~, ~, ir] = unique(T.particle);
    nf = numel(fr);  nr = max(ir);
    k = sub2ind([nf nr], ifr, ir);
    campos = {'X', 'x_mm'; 'Y', 'y_mm'; 'VX', 'vx_mm_s'; 'VY', 'vy_mm_s'; 'S', 'speed_mm_s'; ...
              'Wr', 'omega_deg_s'; 'TH', 'theta_deg'};
    for c = 1:size(campos, 1)
        A = nan(nf, nr);
        A(k) = T.(campos{c, 2});
        P.(campos{c, 1}) = A;
    end
    O = false(nf, nr);
    O(k) = ismember(T.status, {'detectado', 'detectado (umbral relajado)', 'manual'});
    P.OBS = O;
    t = accumarray(ifr, T.t_s, [nf 1], @mean);
end

function orden = emparejar(A, B)
    % Robot identity across a cut: greedy nearest pairs (robots hardly move through the gap; the
    % nearest neighbour is unambiguous, see CLAUDE.md 06/11). orden(i) = column of B for robot i of A.
    n = size(A, 2);
    d = (A(1, :)' - B(1, :)) .^ 2 + (A(2, :)' - B(2, :)) .^ 2;
    d(~isfinite(d)) = Inf;
    orden = zeros(1, n);
    for k = 1:n
        [~, idx] = min(d(:));
        [i, j] = ind2sub(size(d), idx);
        orden(i) = j;
        d(i, :) = Inf;  d(:, j) = Inf;
    end
end

function m = mean_nan(A)
    ok = isfinite(A);
    A(~ok) = 0;
    m = sum(A, 2) ./ sum(ok, 2);
    m(sum(ok, 2) == 0) = NaN;
end

function m = media_grupos(g, x)
    ok = isfinite(x);
    s = accumarray(g(ok), x(ok), [max(g) 1]);
    n = accumarray(g(ok), 1, [max(g) 1]);
    m = s ./ n;
    m(n == 0) = NaN;
end

function [hueco, fr] = hueco_corte(raiz, codigo, k)
    f = fullfile(raiz, 'datos', 'video', 'cortes.json');
    if ~isfile(f), error('%s está partido pero falta datos/video/cortes.json (herramientas/medir_corte.py).', codigo); end
    J = jsondecode(fileread(f));
    campo = ['x' codigo];                       % jsondecode prefixes x to names starting with a digit
    if ~isfield(J, campo), campo = matlab_nombre(codigo); end
    if ~isfield(J, campo), error('%s no figura en cortes.json.', codigo); end
    hueco = J.(campo).hueco_s(k);
    fr = 30000 / 1001 / 10;
    if isfield(J.(campo), 'fr'), fr = J.(campo).fr; end
end

function n = matlab_nombre(s)
    n = regexprep(['x' s], '[^A-Za-z0-9_]', '_');
end
