document.addEventListener('DOMContentLoaded', ()=>{
  const form = document.getElementById('chatForm')
  const msgInput = document.getElementById('msg')
  const box = document.getElementById('chatbox')
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
      // If action_result present, show the human-friendly reply and a compact JSON summary
      if(j.action_result){
        await revealText(loadingEl, j.reply)
        // show details line
        const details = document.createElement('div')
        details.className = 'agent-details'
        const summary = document.createElement('pre')
        summary.textContent = JSON.stringify(j.action_result, null, 2)
        details.appendChild(summary)
        loadingEl.parentNode.appendChild(details)
        box.scrollTop = box.scrollHeight
      } else {
        await revealText(loadingEl, j.reply)
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
