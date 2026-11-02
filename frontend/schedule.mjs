import {fsrs,createEmptyCard} from 'ts-fsrs';
let text='';for await(const chunk of process.stdin)text+=chunk;
const x=JSON.parse(text),now=new Date(x.now);console.log(JSON.stringify(fsrs({enable_fuzz:false}).repeat(x.card||createEmptyCard(now),now)[x.rating].card));
