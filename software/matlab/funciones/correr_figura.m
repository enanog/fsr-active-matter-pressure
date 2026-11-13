function figs = correr_figura(script, codigos)
% CORRER_FIGURA  Run one script of figuras/ with the trials CODIGOS imposed (used by comparar_todo.m)
% and return the figures it opened, oldest first. The script runs in its own workspace, so its
% `clear` does not touch the caller; the imposed trials are removed even on error or Ctrl+C.
    antes = double(findall(0, 'Type', 'figure'));
    setappdata(0, 'lote_ensayos', codigos);
    limpiar = onCleanup(@quitar_lote); %#ok<NASGU>
    ejecutar(script);
    figs = findall(0, 'Type', 'figure');
    figs = figs(~ismember(double(figs), antes));
    [~, orden] = sort(double(figs));
    figs = figs(orden);
end

function ejecutar(script__)
    % Separate workspace: the `clear` at the top of the script only wipes this one
    run(script__);
end

function quitar_lote()
    if isappdata(0, 'lote_ensayos'), rmappdata(0, 'lote_ensayos'); end
end
