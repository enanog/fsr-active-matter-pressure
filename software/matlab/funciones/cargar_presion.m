function R = cargar_presion(filtros)
% CARGAR_PRESION  Pressure of the trials whose code contains any of the texts in FILTROS (also the
% ones without video, e.g. August). 'todos' = every log; {} = pick from a list.
%   R(i).codigo, .etiqueta, .modo, .robots (number from the code), .P (see leer_presion)
    todos = buscar_registros();
    if isempty(todos), error('No hay registros en datos/presion/crudos.'); end
    if nargin < 1, filtros = {}; end
    codigos = elegir_codigos(todos, filtros, 'Registros de presión:');
    raiz = raiz_proyecto();
    for i = 1:numel(codigos)
        p = strsplit(codigos{i}, '_');
        Ri.codigo = codigos{i};
        Ri.etiqueta = etiqueta_ensayo(codigos{i});
        Ri.modo = regexprep(p{3}, '^\d+', '');
        Ri.robots = str2double(regexprep(p{3}, '[A-Za-z]', ''));
        Ri.P = presion_con_cache(raiz, codigos{i});
        if isempty(Ri.P), error('No se pudo leer R_%s.csv', codigos{i}); end
        if i == 1, R = Ri; else, R(i) = Ri; end
    end
end

function P = presion_con_cache(raiz, codigo)
    % Processed log kept in software/matlab/cache/presion_<code>.mat while the log and its FSRScope
    % settings and its R_FEEDBACK in calibracion.csv are unchanged (re-running a figure is then instantaneous).
    fuentes = {fullfile(raiz, 'datos', 'presion', 'crudos', ['R_' codigo '.csv']), ...
               fullfile(raiz, 'datos', 'presion', 'config', [codigo '.json'])};
    firma = zeros(3, 2);
    for k = 1:2
        d = dir(fuentes{k});
        if ~isempty(d), firma(k, :) = [d.datenum, d.bytes]; end
    end
    firma(3, 1) = r_feedback_lista(raiz, codigo);   % only this trial's row of calibracion.csv
    firma(isnan(firma)) = -1;
    cache = fullfile(fileparts(fileparts(mfilename('fullpath'))), 'cache', ['presion_' codigo '.mat']);
    if isfile(cache)
        S = load(cache);
        if isfield(S, 'firma') && isequal(S.firma, firma) && isfield(S, 'version') && S.version == 2
            P = S.P;
            return
        end
    end
    fprintf('Leyendo R_%s.csv (la próxima vez sale de la caché)...\n', codigo);
    P = leer_presion(raiz, codigo);
    if isempty(P), return; end
    if ~isfolder(fileparts(cache)), mkdir(fileparts(cache)); end
    version = 2; %#ok<NASGU>
    save(cache, 'P', 'firma', 'version', '-v7');
end
