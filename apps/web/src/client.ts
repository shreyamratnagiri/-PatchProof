export type Repo = {id:string;name:string;status:string;files:number;digest:string;created_at:string};
export type SymbolRecord = {name:string;line:number;kind:string};
export type Entry = {path:string;symbols:SymbolRecord[];imports:string[];language:string;valid:boolean};
export type Location = {path:string;score:number;lexical:number;semantic:number;graph:number;symbols:SymbolRecord[];imports:string[]};
export type Run = {id:string;repository_id:string;issue_id:string;status:string;method:string;locations:Location[];explanation:string;created_at:string};
export type Candidate = {id:string;path:string;diff:string;rationale:string;model:string;status:string;approved_at:string|null;priority:{score:number;components:Record<string,number>;meaning:string};result:Record<string,unknown>};
export type Graph = {nodes:{id:string;language:string;symbols:number}[];edges:{source:string;target:string}[];note:string};
export class ApiError extends Error {constructor(public status:number,message:string){super(message)}}
export function client(key:string){
  async function req<T>(path:string, init:RequestInit={}):Promise<T>{
    const res=await fetch(path,{...init,headers:{...(init.body instanceof FormData?{}:{'Content-Type':'application/json'}), 'X-PatchProof-Key':key,...init.headers}});
    const raw=await res.text();let value:unknown;
    try{value=JSON.parse(raw)}catch{value={detail:raw}}
    if(!res.ok){
      const detail=(value as {detail?:unknown}).detail;
      const description=typeof detail==='string'?detail:detail!==undefined?JSON.stringify(detail):raw;
      throw new ApiError(res.status,description);
    }
    return value as T;
  }
  const json=(object:unknown):RequestInit=>({method:'POST',body:JSON.stringify(object)});
  return {
    health:()=>req<{ready:boolean;database:string;docker:boolean}>('/ready'),
    status:()=>req<Record<string,unknown>>('/api/status'),
    repos:()=>req<{items:Repo[]}>('/api/repositories'),
    repo:(id:string)=>req<Repo&{entries:Entry[]}>(`/api/repositories/${id}`),
    graph:(id:string)=>req<Graph>(`/api/repositories/${id}/graph`),
    gitImport:(url:string)=>req<Repo>('/api/repositories/git',json({url})),
    import:async(file:File)=>{const body=new FormData();body.append('file',file);return req<Repo>('/api/repositories/import',{method:'POST',body})},
    issues:()=>req<{items:{id:string;repository_id:string;description:string}[]}>('/api/issues'),
    createIssue:(repository_id:string,description:string,expected:string,observed:string)=>req<{id:string}>('/api/issues',json({repository_id,description,expected,observed})),
    start:(issue_id:string,method:string,generate:boolean)=>req<Run>('/api/repairs',json({issue_id,method,generate})),
    runs:()=>req<{items:Run[]}>('/api/repairs'),
    run:(id:string)=>req<Run>(`/api/repairs/${id}`),
    candidates:(id:string)=>req<{items:Candidate[]}>(`/api/repairs/${id}/candidates`),
    generate:(id:string)=>req<Record<string,unknown>>(`/api/repairs/${id}/generate`,{method:'POST'}),
    manual:(id:string,path:string,old:string,updated:string,rationale:string,regression_test:string)=>req<Candidate>(`/api/repairs/${id}/candidates`,json({path,old,new:updated,rationale,regression_test})),
    property:(id:string,variables:string[],assumptions:unknown[],conclusion:unknown)=>req<Record<string,unknown>>(`/api/repairs/${id}/properties`,json({variables,assumptions,conclusion})),
    modelHealth:()=>req<Record<string,unknown>>('/api/model/health'),
    approve:(id:string,candidate_id:string)=>req<Record<string,unknown>>(`/api/repairs/${id}/candidates/${candidate_id}/approve`,{method:'POST'}),
    patch:async(id:string,candidate_id:string)=>{
      const response=await fetch(`/api/repairs/${id}/candidates/${candidate_id}/patch`,{headers:{'X-PatchProof-Key':key}});
      if(!response.ok)throw new ApiError(response.status,await response.text());
      return response.blob();
    },
    verify:(id:string,candidate_id:string)=>req<Record<string,unknown>>(`/api/repairs/${id}/verify?candidate_id=${encodeURIComponent(candidate_id)}`,{method:'POST'}),
    job:(id:string)=>req<{id:string;status:string;candidate_id?:string;result?:Record<string,unknown>}>(`/api/jobs/${id}`),
    report:(id:string)=>req<Record<string,unknown>>(`/api/repairs/${id}/report`),
    cancel:(id:string)=>req<Record<string,unknown>>(`/api/jobs/${id}/cancel`,{method:'POST'}),
  };
}
