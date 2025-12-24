document.addEventListener('DOMContentLoaded', ()=>{
  const form = document.getElementById('chatForm')
  const msgInput = document.getElementById('msg')
  const box = document.getElementById('chatbox')
  if(!form || !box) return
  form.addEventListener('submit', async (e)=>{
    e.preventDefault()
    const text = msgInput.value.trim()
    if(!text) return
    append('You', text)
    msgInput.value = ''
    // show loading placeholder and disable input
    const loadingEl = append('Agent', 'Agent is typing...', {loading:true})
    msgInput.disabled = true
    const btn = form.querySelector('button')
    if(btn) btn.disabled = true
    try{
      const res = await fetch('/agent/chat', {
        method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({message: text})
      })
      const j = await res.json()
      // If preview is returned, show preview UI and confirm button
      if(j.requires_confirmation && j.raw_action){
        await revealText(loadingEl, j.reply)
        const previewBox = document.createElement('div')
        previewBox.className = 'agent-details'
        const pre = document.createElement('pre')
        pre.textContent = JSON.stringify(j.preview, null, 2)
        previewBox.appendChild(pre)
        const btn = document.createElement('button')
        btn.textContent = 'Confirm and Execute'
        btn.style.marginTop = '6px'
        btn.addEventListener('click', async ()=>{
          btn.disabled = true
          btn.textContent = 'Executing...'
          try{
            const execRes = await fetch('/agent/chat', {
              method:'POST', headers:{'Content-Type':'application/json'},
              body: JSON.stringify({message: text, confirm: true, action: j.raw_action})
            })
            const execJson = await execRes.json()
            const execDetails = document.createElement('div')
            execDetails.className = 'agent-details'
            const execPre = document.createElement('pre')
            execPre.textContent = JSON.stringify(execJson.action_result || execJson, null, 2)
            execDetails.appendChild(execPre)
            previewBox.parentNode.appendChild(execDetails)
            // show executed reply
            await revealText(loadingEl, execJson.reply || 'Done')
            saveHistory()
          }catch(err){
            btn.textContent = 'Error'
          }
        })
        previewBox.appendChild(btn)
        loadingEl.parentNode.appendChild(previewBox)
        box.scrollTop = box.scrollHeight
        saveHistory()
      } else if(j.action_result){
        await revealText(loadingEl, j.reply)
        // show details line
        const details = document.createElement('div')
        details.className = 'agent-details'
        const summary = document.createElement('pre')
        summary.textContent = JSON.stringify(j.action_result, null, 2)
        details.appendChild(summary)
        loadingEl.parentNode.appendChild(details)
        box.scrollTop = box.scrollHeight
        saveHistory()
      } else {
        await revealText(loadingEl, j.reply)
        saveHistory()
      }
    }catch(err){
      loadingEl.innerHTML = escapeHtml('Error: '+err.message)
      loadingEl.classList.remove('loading')
    } finally{
      msgInput.disabled = false
      if(btn) btn.disabled = false
      msgInput.focus()
    }
  })

  function append(who, text){
    const el = document.createElement('div')
    el.className='msg'
    if(who === 'Agent') el.classList.add('agent')
    const userSpan = `<span class="user">${who}:</span>`
    el.innerHTML = `${userSpan} <span class="text">${escapeHtml(text)}</span>`
    const textNode = el.querySelector('.text')
    if(arguments[2] && arguments[2].loading){
      textNode.classList.add('loading')
    }
    box.appendChild(el)
    box.scrollTop = box.scrollHeight
    return textNode
  }

  // Persist chat history to localStorage
  function loadHistory(){
    try{
      const raw = localStorage.getItem('chat_history')
      if(!raw) return
      const items = JSON.parse(raw)
      for(const it of items){
        append(it.who, it.text)
        if(it.details){
          const details = document.createElement('div')
          details.className = 'agent-details'
          const pre = document.createElement('pre')
          pre.textContent = JSON.stringify(it.details, null, 2)
          details.appendChild(pre)
          box.appendChild(details)
        }
      }
    }catch(e){console.warn('failed to load chat history', e)}
  }

  function saveHistory(){
    try{
      const nodes = box.querySelectorAll('.msg')
      const out = []
      for(const n of nodes){
        const who = n.querySelector('.user') ? n.querySelector('.user').textContent.replace(':','') : 'Agent'
        const text = n.querySelector('.text') ? n.querySelector('.text').textContent : ''
        out.push({who, text})
      }
      localStorage.setItem('chat_history', JSON.stringify(out))
    }catch(e){console.warn('failed to save chat history', e)}
  }

  // load saved history on start
  loadHistory()

  // undo button handler (if present)
  const undoBtn = document.getElementById('undoAiBtn')
  if(undoBtn){
    undoBtn.addEventListener('click', async ()=>{
      undoBtn.disabled = true
      undoBtn.textContent = 'Undoing...'
      try{
        const res = await fetch('/agent/undo', {method:'POST'})
        const j = await res.json()
        append('Agent', j.ok ? (j.restored ? `✅ Restored ${j.restored}` : '✅ Undo completed') : `❌ ${j.message}`)
        saveHistory()
      }catch(e){
        append('Agent', 'Error undoing: '+(e.message||e))
      }finally{
        undoBtn.disabled = false
        undoBtn.textContent = 'Undo last AI action'
      }
    })
  }

  // reveal text char-by-char in the given element
  function revealText(el, text){
    return new Promise((resolve)=>{
      el.classList.remove('loading')
      el.innerHTML = ''
      let i = 0
      const s = String(text || '')
      const speed = 18 // ms per char
      function step(){
        if(i < s.length){
          el.innerHTML += escapeHtml(s.charAt(i))
          i++
          box.scrollTop = box.scrollHeight
          setTimeout(step, speed)
        }else{
          resolve()
        }
      }
      step()
    })
  }

  function escapeHtml(s){ return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;') }
})
