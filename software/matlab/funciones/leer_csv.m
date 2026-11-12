function T = leer_csv(archivo, numericas, textos)
% LEER_CSV  Read only the requested columns of a CSV with a header line (quotes optional).
%   T = leer_csv(archivo, {'frame', 't_s'}, {'status'})  -> T.frame, T.t_s (double), T.status (cell)
% Missing columns come back as NaN (numeric) or '' (text). Column names are case-insensitive; characters
% not valid in a MATLAB field name become '_' ('timestamp(ms)' -> T.timestamp_ms_).
% Works in MATLAB and Octave (no readtable).
    if nargin < 3, textos = {}; end
    fid = fopen(archivo, 'r');
    if fid < 0, error('No se puede abrir %s', archivo); end
    cab = fgetl(fid);
    resto = fread(fid, Inf, '*char')';
    fclose(fid);
    resto = strrep(strrep(resto, '"', ''), char(13), '');
    nombres = lower(strtrim(strsplit(strrep(cab, '"', ''), ',')));
    if ~isempty(nombres) && isempty(nombres{end}), nombres(end) = []; end   % trailing comma
    nl = find(resto == sprintf('\n'), 1);
    if isempty(nl), nl = numel(resto) + 1; end
    n_campos = max(numel(nombres), sum(resto(1:nl - 1) == ',') + 1);   % rows with a trailing comma
    fmt = repmat({'%*s'}, 1, n_campos);
    pedidas = [numericas(:); textos(:)]';
    idx = zeros(1, numel(pedidas));
    for k = 1:numel(pedidas)
        i = find(strcmp(nombres, lower(pedidas{k})), 1);
        if ~isempty(i)
            idx(k) = i;
            if k <= numel(numericas), fmt{i} = '%f'; else, fmt{i} = '%s'; end
        end
    end
    C = textscan(resto, strjoin(fmt, ''), 'Delimiter', ',', 'EmptyValue', NaN, ...
                 'Whitespace', '', 'ReturnOnError', false);
    usadas = sort(idx(idx > 0));
    n = 0;
    if ~isempty(C), n = numel(C{1}); end
    for k = 1:numel(pedidas)
        nom = regexprep(pedidas{k}, '[^A-Za-z0-9_]', '_');
        if idx(k) == 0
            if k <= numel(numericas), T.(nom) = nan(n, 1); else, T.(nom) = repmat({''}, n, 1); end
        else
            T.(nom) = C{usadas == idx(k)};
        end
    end
end
