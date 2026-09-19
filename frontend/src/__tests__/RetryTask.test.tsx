import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { vi, test, expect } from 'vitest';
import { JobRow } from '../features/jobs/JobRow';
import { retryJob } from '../shared/api/jobs';
vi.mock('../shared/api/jobs',()=>({retryJob:vi.fn(),cancelJob:vi.fn()}));
test('retries a failed task and surfaces a failed submission',async()=>{
  const changed=vi.fn();const opened=vi.fn();
  vi.mocked(retryJob).mockRejectedValueOnce(new Error('队列暂不可用')).mockResolvedValueOnce({success:true,job_id:'new'});
  render(<JobRow job={{id:'old',job_id:'old',status:'failed',job_type:'api_request',progress:100,module:'statistical.analyze'}} onJobChanged={changed} onOpenDetails={opened}/>);
  fireEvent.click(screen.getByRole('button',{name:'重试任务'}));
  expect(await screen.findByRole('alert')).toHaveTextContent('队列暂不可用');
  fireEvent.click(screen.getByRole('button',{name:'重试任务'}));
  await waitFor(()=>expect(changed).toHaveBeenCalledOnce());
  expect(retryJob).toHaveBeenLastCalledWith('old');expect(opened).not.toHaveBeenCalled();
});
