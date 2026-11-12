function D = cargar_ensayos(filtros)
% CARGAR_ENSAYOS  Load the trials whose code contains any of the texts in FILTROS
% (cell, e.g. {'20260924', '20261030_1600'}). 'todos' = every trial; {} = pick from a list.
% Returns a struct array (see cargar_ensayo), oldest first.
    todos = buscar_ensayos();
    if isempty(todos)
        error('No hay trayectorias en datos/video/trayectorias.');
    end
    if nargin >= 1 && ischar(filtros) && strcmpi(filtros, 'todos')
        codigos = todos;
    elseif nargin < 1 || isempty(filtros)
        textos = cellfun(@etiqueta_ensayo, todos, 'UniformOutput', false);
        [sel, ok] = listdlg('ListString', textos, 'SelectionMode', 'multiple', ...
                            'PromptString', 'Ensayos a graficar:', 'ListSize', [260 300]);
        if ~ok || isempty(sel), error('No se eligió ningún ensayo.'); end
        codigos = todos(sel);
    else
        if ischar(filtros), filtros = {filtros}; end
        usar = false(size(todos));
        for k = 1:numel(filtros)
            usar = usar | ~cellfun(@isempty, strfind(todos, filtros{k}));
        end
        codigos = todos(usar);
        if isempty(codigos)
            error('Ningún ensayo coincide con %s. Disponibles:\n  %s', strjoin(filtros, ', '), strjoin(todos, '\n  '));
        end
    end
    for i = 1:numel(codigos)
        Di = cargar_ensayo(codigos{i});
        if i == 1, D = Di; else, D(i) = Di; end
    end
end
