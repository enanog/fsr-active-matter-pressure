function [R, nota] = r_feedback_lista(raiz, codigo)
% R_FEEDBACK_LISTA  Feedback resistor [ohm] of a log taken from datos/presion/calibracion.csv.
%   Columns: codigo, r_feedback_ohm, nota. 'codigo' may be the full code or its start (e.g.
%   '20260924_1600' or '20260924'); the longest matching entry wins. Empty r_feedback_ohm, or a code
%   not in the list, gives R = NaN (then the FSRScope settings / firmware factor are used).
%   Do not use commas inside 'nota'.
    R = NaN;  nota = '';
    f = fullfile(raiz, 'datos', 'presion', 'calibracion.csv');
    if ~isfile(f), return; end
    T = leer_csv(f, {'r_feedback_ohm'}, {'codigo', 'nota'});
    largo = 0;
    for i = 1:numel(T.codigo)
        c = strtrim(T.codigo{i});
        if isempty(c) || numel(c) <= largo || ~strncmp(codigo, c, numel(c)), continue; end
        largo = numel(c);
        R = T.r_feedback_ohm(i);
        nota = strtrim(T.nota{i});
    end
    if ~(isfinite(R) && R > 0), R = NaN; nota = ''; end
end
