import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { Stage6History } from "../features/scripthub/stages/Stage6History";
import { MemoryRouter } from "react-router-dom";
import { getJob, getJobResults, listJobs } from "../shared/api/jobs";

vi.mock("../shared/api/jobs", () => ({ listJobs: vi.fn(), getJob: vi.fn(), getJobResults: vi.fn(), cancelJob: vi.fn() }));
const job = (id: string) => ({ id, job_id: id, module: id, status: "completed", progress: 100 });
const result = (id: string) => ({ success: true, job: job(id), status: "completed", assets: [], result: {}, outputs: [{ kind: "html", label: `${id}报告`, url: `/${id}.html` }] });
const renderHistory = (element: React.ReactNode) => render(element, { wrapper: MemoryRouter });
beforeEach(() => {
  vi.mocked(listJobs).mockResolvedValue({ success: true, jobs: [job('任务A'), job('任务B')] } as never);
  vi.mocked(getJob).mockImplementation(async id => ({ success: true, job: job(id) }) as never);
  vi.mocked(getJobResults).mockImplementation(async id => result(id) as never);
});
afterEach(() => { cleanup(); vi.resetAllMocks(); vi.useRealTimers(); });

describe("analysis history", () => {
  it("opens a result and sends search to the history API", async () => {
    renderHistory(<Stage6History projectId="p1" onSelectResult={vi.fn()} />);
    fireEvent.click(await screen.findByText('任务A'));
    expect(await screen.findByRole('link', { name: '打开交互报告' })).toHaveAttribute('href', '/任务A.html');
    vi.mocked(listJobs).mockResolvedValue({success:true,jobs:[job('任务B')],total:1} as never);
    fireEvent.change(screen.getByRole('searchbox'), { target: { value: '任务B' } });
    await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('共 1 项任务'));
    expect(listJobs).toHaveBeenLastCalledWith(expect.objectContaining({search:'任务B',offset:0}));
  });
  it("ignores an earlier result after another job is selected", async () => {
    let resolveOld!: (value: unknown) => void;
    vi.mocked(getJobResults).mockImplementationOnce(() => new Promise(resolve => { resolveOld = resolve; }) as never);
    renderHistory(<Stage6History projectId="p1" onSelectResult={vi.fn()} />);
    fireEvent.click(await screen.findByText('任务A'));
    await waitFor(() => expect(getJobResults).toHaveBeenCalledWith('任务A'));
    fireEvent.click(screen.getByText('任务B'));
    expect(await screen.findByRole('link', { name: '打开交互报告' })).toHaveAttribute('href', '/任务B.html');
    await act(async () => { resolveOld(result('任务A')); });
    expect(screen.getByRole('link', { name: '打开交互报告' })).toHaveAttribute('href', '/任务B.html');
  });
  it("resets the project and ignores an old pending list", async () => {
    let resolveOld!: (value: unknown) => void;
    vi.mocked(listJobs).mockImplementationOnce(() => new Promise(resolve => { resolveOld = resolve; }) as never);
    const view = renderHistory(<Stage6History projectId="p1" onSelectResult={vi.fn()} />);
    view.rerender(<Stage6History projectId="p2" onSelectResult={vi.fn()} />);
    await screen.findByText('任务B');
    await act(async () => { resolveOld({ success: true, jobs: [job('旧项目任务')] }); });
    expect(screen.queryByText('旧项目任务')).not.toBeInTheDocument();
    expect(listJobs).toHaveBeenLastCalledWith(expect.objectContaining({ projectId: 'p2', limit: 50, offset:0 }));
  });
  it("retries failed results and starts a new analysis from the empty history", async () => {
    const onSelect = vi.fn();
    vi.mocked(getJobResults).mockRejectedValueOnce(new Error('暂时不可用'));
    const view = renderHistory(<Stage6History projectId="p1" onSelectResult={onSelect} />);
    fireEvent.click(await screen.findByText('任务A'));
    expect(await screen.findByRole('alert')).toHaveTextContent('暂时不可用');
    fireEvent.click(screen.getByRole('button', { name: '重新读取结果' }));
    await screen.findByRole('link', { name: '打开交互报告' });
    vi.mocked(listJobs).mockResolvedValue({ success: true, jobs: [] });
    view.rerender(<Stage6History projectId="empty" onSelectResult={onSelect} />);
    await screen.findByText('暂无分析历史');
    fireEvent.click(screen.getByRole('button', { name: '新建分析' }));
    expect(onSelect).toHaveBeenCalledWith('');
    expect(screen.queryByRole('link', { name: '打开交互报告' })).not.toBeInTheDocument();
  });
  it("waits for a request to finish before scheduling the next poll", async () => {
    vi.useFakeTimers();
    let resolveList!: (value: unknown) => void;
    vi.mocked(listJobs).mockImplementationOnce(() => new Promise(resolve => { resolveList = resolve; }) as never);
    renderHistory(<Stage6History projectId="slow" onSelectResult={vi.fn()} />);
    await act(async () => { await vi.advanceTimersByTimeAsync(15000); });
    expect(listJobs).toHaveBeenCalledTimes(1);
    await act(async () => { resolveList({ success: true, jobs: [] }); });
    await act(async () => { await vi.advanceTimersByTimeAsync(5000); });
    expect(listJobs).toHaveBeenCalledTimes(2);
  });
});
