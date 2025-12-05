import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { MapPin } from "lucide-react";

type State = "CA" | "WA" | "IL" | "OTHER" | null;

const STATES = [
  { value: "Alabama", display: "Alabama" },
  { value: "Alaska", display: "Alaska" },
  { value: "Arizona", display: "Arizona" },
  { value: "Arkansas", display: "Arkansas" },
  { value: "California", display: "California" },
  { value: "Colorado", display: "Colorado" },
  { value: "Connecticut", display: "Connecticut" },
  { value: "Delaware", display: "Delaware" },
  { value: "Florida", display: "Florida" },
  { value: "Georgia", display: "Georgia" },
  { value: "Hawaii", display: "Hawaii" },
  { value: "Idaho", display: "Idaho" },
  { value: "Illinois", display: "Illinois" },
  { value: "Indiana", display: "Indiana" },
  { value: "Iowa", display: "Iowa" },
  { value: "Kansas", display: "Kansas" },
  { value: "Kentucky", display: "Kentucky" },
  { value: "Louisiana", display: "Louisiana" },
  { value: "Maine", display: "Maine" },
  { value: "Maryland", display: "Maryland" },
  { value: "Massachusetts", display: "Massachusetts" },
  { value: "Michigan", display: "Michigan" },
  { value: "Minnesota", display: "Minnesota" },
  { value: "Mississippi", display: "Mississippi" },
  { value: "Missouri", display: "Missouri" },
  { value: "Montana", display: "Montana" },
  { value: "Nebraska", display: "Nebraska" },
  { value: "Nevada", display: "Nevada" },
  { value: "New Hampshire", display: "New Hampshire" },
  { value: "New Jersey", display: "New Jersey" },
  { value: "New Mexico", display: "New Mexico" },
  { value: "New York", display: "New York" },
  { value: "North Carolina", display: "North Carolina" },
  { value: "North Dakota", display: "North Dakota" },
  { value: "Ohio", display: "Ohio" },
  { value: "Oklahoma", display: "Oklahoma" },
  { value: "Oregon", display: "Oregon" },
  { value: "Pennsylvania", display: "Pennsylvania" },
  { value: "Rhode Island", display: "Rhode Island" },
  { value: "South Carolina", display: "South Carolina" },
  { value: "South Dakota", display: "South Dakota" },
  { value: "Tennessee", display: "Tennessee" },
  { value: "Texas", display: "Texas" },
  { value: "Utah", display: "Utah" },
  { value: "Vermont", display: "Vermont" },
  { value: "Virginia", display: "Virginia" },
  { value: "Washington", display: "Washington" },
  { value: "West Virginia", display: "West Virginia" },
  { value: "Wisconsin", display: "Wisconsin" },
  { value: "Wyoming", display: "Wyoming" }
];

interface InlineStateSelectorProps {
  selectedState: State;
  onStateChange: (state: State) => void;
  showLabel?: boolean;
  compact?: boolean;
}

function stateToCode(stateName: string): State {
  if (stateName === "California") return "CA";
  if (stateName === "Washington") return "WA";
  if (stateName === "Illinois") return "IL";
  return "OTHER";
}

function codeToStateName(code: State): string {
  if (code === null) return "";
  if (code === "CA") return "California";
  if (code === "WA") return "Washington";
  if (code === "IL") return "Illinois";
  return "";
}

export function InlineStateSelector({ selectedState, onStateChange, showLabel = true, compact = false }: InlineStateSelectorProps) {
  const currentStateName = codeToStateName(selectedState);
  
  const handleChange = (value: string) => {
    onStateChange(stateToCode(value));
  };

  return (
    <div className={`flex items-center gap-2 ${compact ? '' : 'bg-muted/50 rounded-lg px-3 py-2'}`}>
      {showLabel && (
        <div className="flex items-center gap-1.5 text-muted-foreground">
          <MapPin className="h-4 w-4" />
          <span className="text-sm font-medium">Your State:</span>
        </div>
      )}
      <Select value={currentStateName || undefined} onValueChange={handleChange}>
        <SelectTrigger className={`${compact ? 'w-[160px]' : 'w-[180px]'} bg-background`}>
          <SelectValue placeholder="Select state..." />
        </SelectTrigger>
        <SelectContent className="max-h-[200px]">
          {STATES.map((state) => (
            <SelectItem key={state.value} value={state.value}>
              {state.display}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}
