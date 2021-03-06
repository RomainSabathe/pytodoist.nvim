
" The VimL/VimScript code is included in this sample plugin to demonstrate the
" two different approaches but it is not required you use VimL. Feel free to
" delete this code and proceed without it.

"nnoremap <buffer><silent> <leader>T :call LoadTasks()<CR>
"nnoremap <buffer><silent> dd :call DeleteTask()<CR>
nnoremap <silent> <leader>T :call LoadTasks()<CR>

:autocmd FileType todoist nnoremap <buffer><silent> X :call CompleteTask()<CR>

:autocmd FileType todoist nnoremap <buffer><silent> m :call MoveTask()<CR>
:autocmd FileType todoist vnoremap <buffer><silent> m :call MoveTask()<CR>

:autocmd FileType todoist nnoremap <buffer><silent> <leader>l :call AssignLabel()<CR>

:autocmd FileType todoist nnoremap <buffer><silent> o :normal! o[ ]  <esc>i<kDel>
:autocmd FileType todoist nnoremap <buffer><silent> O :normal! O[ ]  <esc>i<kDel>


function! CaptureFzfOutput(cmd)
    let g:fzf_output = a:cmd
endfunction

function! ResetFzfOutput()
    if exists("g:fzf_output")
        unlet g:fzf_output
    endif
endfunction
