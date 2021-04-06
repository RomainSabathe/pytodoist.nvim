
" The VimL/VimScript code is included in this sample plugin to demonstrate the
" two different approaches but it is not required you use VimL. Feel free to
" delete this code and proceed without it.

"nnoremap <buffer><silent> <leader>T :call LoadTasks()<CR>
"nnoremap <buffer><silent> dd :call DeleteTask()<CR>
nnoremap <silent> <leader>T :call LoadTasks()<CR>
:autocmd FileType todoist nnoremap <buffer><silent> dd :call DeleteTask()<CR>
:autocmd FileType todoist vnoremap <buffer><silent> d :call DeleteTask()<CR>
:autocmd FileType todoist nnoremap <buffer><silent> u :call Undo()<CR>
:autocmd FileType todoist nnoremap <buffer><silent> <c-r> :call Redo()<CR>
:autocmd FileType todoist nnoremap <buffer><silent> x :call CompleteTask()<CR>
:autocmd FileType todoist nnoremap <buffer><silent> >> :call MakeChild()<CR>
:autocmd FileType todoist nnoremap <buffer><silent> << :call UnmakeChild()<CR>

":highlight MyGroup ctermbg=green guibg=green
":let m = matchadd("MyGroup", "something")
