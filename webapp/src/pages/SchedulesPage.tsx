import { Header } from '../components/layout/Header'
import { ScheduleList } from '../components/schedules/ScheduleList'

export function SchedulesPage() {
  return (
    <div className="flex flex-col h-full">
      <Header title="Schedules" />
      <ScheduleList />
    </div>
  )
}
