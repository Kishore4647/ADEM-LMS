import { test, expect } from '@playwright/test'

const nodes = ['class','subject','chapter','topic','sub_topic'].map((level,index)=>({id:index+1,board_id:1,parent_id:index||null,name:['Class 7','Mathematics','Expressions','Arithmetic','Order of operations'][index],level,sequence:1}))
const data = {
  schools:[{id:1,name:'Example School',code:'EX',is_active:true}], users:[{id:1,email:'admin@example.com',full_name:'Example Admin',role:'super_admin',is_active:true,school_ids:[1]}],boards:[{id:1,name:'CBSE'}],nodes,
  students:[{id:1,user_id:5,school_id:1,class_node_id:1,name:'Example Student',admission_number:'ST01'}],teaching:[{id:1,user_id:3,school_id:1,subject_id:2}],
  assets:[{id:1,school_id:1,subtopic_id:5,title:'Introduction to expressions',kind:'video',drive_id:'example',file_id:null,published:true,issue:null}],
  sessions:[{id:1,school_id:1,subject_id:2,trainer_id:3,session_date:'2026-10-26',period:'2026-Q1',subtopic_ids:[5],notes:'Covered arithmetic expressions',status:'submitted',review_comment:''}],
  marks:[{id:1,student_id:1,subject_node_id:2,component:'assessment',academic_period:'2026-Q1',title:'Session #1',obtained_marks:8,maximum_marks:10,is_absent:false}],
  attendance:[{mark_id:1,session_id:1,student_id:1,manual_present:true,final_status:'Present'}],
  question_sets:[{id:1,school_id:1,subtopic_id:5,title:'Arithmetic MCQ',difficulty:'easy',status:'dispatched',question_count:1,policy:{correct_marks:2,incorrect_penalty:0,max_attempts:1,counted_attempt:'best'}}],
  assignments:[{id:1,question_set_id:1,student_id:1,score:null,submitted_at:null,history:[]}],publications:[],
}
for(const role of ['super_admin','content_uploader','ist','school_management','student']) {
  test(`${role} can navigate its complete workspace without browser errors`,async({page})=>{
    const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message))
    await page.route('**/api/**',async route=>{
      const path=new URL(route.request().url()).pathname
      let body:unknown=[]
      if(path==='/api/auth/me')body={id:role==='super_admin'?1:role==='ist'?3:5,email:`${role}@example.com`,full_name:'Example User',role,is_active:true,school_ids:[1]}
      else if(path==='/api/workspace/data')body=data
      else if(path==='/api/workspace/leaderboard')body={configured:false,rows:[]}
      else if(path==='/api/workspace/community/settings')body=null
      else if(path==='/api/workspace/attempts/1')body={id:1,title:'Arithmetic MCQ',questions:[{prompt:'<p>What is 2 + 2?</p>',options:['1','2','3','4'],hint:'<p>Add two and two.</p>'}],policy:{correct_marks:2,incorrect_penalty:0,max_attempts:1,counted_attempt:'best'},attempts:0,remaining:true,score:null,history:[]}
      await route.fulfill({json:body})
    })
    await page.goto('/')
    await expect(page.getByRole('heading',{name:'Overview',exact:true})).toBeVisible()
    const buttons=page.locator('.sidebar nav button')
    const names=await buttons.allTextContents()
    for(const name of names) {
      await buttons.filter({hasText:name.trim()}).click()
      await expect(page.locator('.page-header h1')).toBeVisible()
    }
    expect(errors).toEqual([])
    if(role==='super_admin') {
      await buttons.filter({hasText:'Overview'}).click()
      await page.screenshot({path:'test-results/admin-desktop.png',fullPage:true})
      await page.setViewportSize({width:390,height:844})
      await expect(page.locator('.menu-toggle')).toBeVisible()
      await page.screenshot({path:'test-results/admin-mobile.png',fullPage:true})
    }
    if(role==='student') {
      await buttons.filter({hasText:'Assessments'}).click()
      await page.getByRole('button',{name:'Attempt',exact:true}).click()
      await expect(page.getByText('What is 2 + 2?')).toBeVisible()
      await expect(page.getByText('Add two and two.')).toBeVisible()
      expect(await page.locator('.answer').count()).toBe(4)
      await page.screenshot({path:'test-results/student-assessment.png',fullPage:true})
    }
  })
}

test('Google sign-in screen contains the login URL and handles unauthorised session',async({page})=>{
  await page.route('**/api/auth/me',route=>route.fulfill({status:401,json:{detail:'Authentication required'}}))
  await page.route('**/api/public/hall-of-fame',route=>route.fulfill({json:[]}))
  await page.goto('/')
  await expect(page.getByRole('link',{name:'Continue with Google'})).toHaveAttribute('href','http://localhost:8000/api/auth/google/login')
  await page.screenshot({path:'test-results/login.png',fullPage:true})
})

test('IST class roster submits marks as one batch with variable maximum',async({page})=>{
  let saved: {marks:{maximum_marks:number;obtained_marks:number;component:string}[]}|null=null
  await page.route('**/api/**',async route=>{
    const path=new URL(route.request().url()).pathname
    if(path==='/api/auth/me')return route.fulfill({json:{id:3,email:'ist@example.com',full_name:'Example Trainer',role:'ist',is_active:true,school_ids:[1]}})
    if(path==='/api/workspace/data')return route.fulfill({json:data})
    if(path==='/api/workspace/marks/batch'){saved=route.request().postDataJSON();return route.fulfill({json:{saved:1,ids:[2]}})}
    return route.fulfill({json:[]})
  })
  await page.goto('/')
  await page.locator('.sidebar nav').getByRole('button',{name:'Marks',exact:false}).click()
  const roster=page.locator('section.panel').filter({has:page.getByRole('heading',{name:'Class roster mark entry',exact:true})})
  await roster.getByRole('combobox',{name:'School',exact:true}).selectOption('1')
  await roster.getByRole('combobox',{name:'Subject',exact:true}).selectOption('2')
  await roster.getByRole('combobox',{name:'Component',exact:true}).selectOption('activity')
  await roster.getByLabel('Academic year / quarter',{exact:true}).fill('2026-Q2')
  await roster.getByLabel('Assessment title',{exact:true}).fill('Activity sheet 2')
  await roster.getByLabel('Maximum marks',{exact:true}).fill('20')
  await roster.getByLabel('Mark for Example Student',{exact:true}).fill('15')
  await roster.getByRole('button',{name:'Save class marks',exact:true}).click()
  await expect(roster.getByText('Saved 1 student record(s). Blank rows were left unrecorded.')).toBeVisible()
  expect(saved?.marks[0]).toMatchObject({maximum_marks:20,obtained_marks:15,component:'activity'})
})
