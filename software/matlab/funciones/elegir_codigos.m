function codigos = elegir_codigos(todos, filtros, titulo)
% ELEGIR_CODIGOS  Codes of TODOS selected by FILTROS:
%   'todos' -> every code; {} -> pick list with funciones/ensayos_base.m preselected;
%   cell/char -> codes containing any of the texts (e.g. {'20261030', '20261106_1600'}).
% While comparar_todo.m runs a script, the trials chosen there replace FILTROS.
% The selection is kept (appdata 'codigos_actuales') so nueva_figura and guardar_figura can name the
% window and the files after the measurements they show.
    if nargin < 2, filtros = {}; end
    if nargin < 3, titulo = 'Ensayos:'; end
    if isappdata(0, 'lote_ensayos'), filtros = getappdata(0, 'lote_ensayos'); end
    if isstring(filtros), filtros = cellstr(filtros); end
    if ischar(filtros) && strcmpi(filtros, 'todos')
        codigos = todos;
    elseif isempty(filtros)
        textos = cellfun(@etiqueta_ensayo, todos, 'UniformOutput', false);
        marcados = find(coincide(todos, ensayos_base()));
        if isempty(marcados), marcados = 1; end
        [sel, ok] = listdlg('ListString', textos, 'SelectionMode', 'multiple', ...
                            'PromptString', titulo, 'ListSize', [260 300], 'InitialValue', marcados);
        if ~ok || isempty(sel), error('No se eligió ningún ensayo.'); end
        codigos = todos(sel);
    else
        if ischar(filtros), filtros = {filtros}; end
        codigos = todos(coincide(todos, filtros));
        if isempty(codigos)
            error('Ningún ensayo coincide con %s. Disponibles:\n  %s', strjoin(filtros, ', '), strjoin(todos, '\n  '));
        end
    end
    setappdata(0, 'codigos_actuales', codigos);
end

function usar = coincide(todos, filtros)
    % True for every code that contains any of the texts in FILTROS
    usar = false(size(todos));
    for k = 1:numel(filtros)
        usar = usar | ~cellfun(@isempty, strfind(todos, filtros{k}));
    end
end
